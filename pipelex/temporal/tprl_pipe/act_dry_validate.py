"""Temporal activity running the whole /validate job — validation sweep + graph dry-run — in one process.

When Temporal is enabled, the API dispatches the whole ``/validate`` job to a worker as ONE
activity (via the one-step wrapper workflow ``WfDryValidate``) instead of running the sweep
API-side and the graph dry-run as a top-level worker workflow. The body is fully in-process:

- the **sweep** is :func:`pipelex.pipeline.validate_bundle.validate_bundle` — the exact function
  the direct-mode ``/validate`` route calls, so both backends surface the SAME error contract
  (the categorized ``ValidateBundleError`` cascade) and the same status map. It is already
  Temporal-safe: ``BundleValidator.validate_pipes`` scopes its own in-process router and dry
  content generator and runs a locally-constructed ``PipeRun``.
- the **graph dry-run** is ``dry_run_pipe_in_process`` — in-process by construction (local
  ``PipeRun`` under ``scoped_event_log`` / ``scoped_pipe_router`` / ``scoped_content_generator``),
  tracing into an in-memory event log; the ``GraphSpec`` rides back on the activity result. No
  NDJSON file, no DynamoDB round-trip, no usage/cost reporting.

Library lifecycle (D4): the library is loaded ONCE — ``validate_bundle`` loads it and leaves it
current on success (its D6 loaded-on-success contract; it owns teardown on failure), the graph
runs against the same library, and this activity tears it down once in its ``finally``.

Error contract (D3): the output carries the success-only status map + the best-effort
``GraphSpec``. Validation failures (blueprint/factory/wiring errors, unexpected pipe failures,
strict-mode signature refusals) RAISE out of ``validate_bundle`` as ``ValidateBundleError`` and
cross the boundary as structured ``ErrorReport``s via ``convert_pipelex_errors`` — the API
renders them as the same RFC 7807 422 the direct path produces (identical ``error_type``,
``error_domain=input``, caller-facing message carrying the offending refs).

Graph best-effort (D5): only the expected dry-run-failure shapes — ``DryRunError`` /
``PipeRunError`` / ``PipeRouterError`` (the run-failure wrappers) and pydantic
``ValidationError`` / polyfactory ``FactoryException`` (the mock-input mint shapes, mirroring
``BundleValidator._classify_pipe``) — degrade to ``graph_spec=None``. Any other ``PipelexError``
(config, library, tracing infra) and every non-Pipelex programming bug propagate and fail the
activity, mirroring ``assemble_tracing``'s bug-propagation policy.
"""

from pathlib import Path

from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError
from temporalio import activity

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_required_pipe,
    set_current_library,
)
from pipelex.pipe_run.dry_run_pipeline import dry_run_pipe_in_process
from pipelex.pipe_run.exceptions import DryRunError, PipeRouterError, PipeRunError
from pipelex.pipeline.bundle_validator import DryRunOutput
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


class DryValidateArg(BaseModel):
    """Input for the dry-run+validation activity (serializable across the Temporal boundary)."""

    mthds_contents: list[str] | None = None
    library_dirs: list[str] | None = None
    allow_signatures: bool = False
    # Optional explicit pipe selection for the graph arm; defaults to the bundle's declared
    # main_pipe (qualified from the first blueprint declaring one). The sweep always covers the
    # whole bundle; no graph is produced when neither this nor a main_pipe is set.
    pipe_code: str | None = None


class DryValidateResult(BaseModel):
    """Output of the dry-run+validation activity: success-only status map + best-effort graph (D3)."""

    dry_run_outputs: dict[str, DryRunOutput]
    graph_spec: GraphSpec | None = None


@activity.defn(name="act_dry_validate")
@convert_pipelex_errors
async def act_dry_validate(arg: DryValidateArg) -> DryValidateResult:
    """Run the validation sweep + the in-memory graph dry-run against one library, in-process.

    Raises (crossing as structured ``ErrorReport``s via ``convert_pipelex_errors``):
        ValidateBundleError: any validation failure — blueprint/factory/wiring errors, unexpected
            dry-run pipe failures, strict-mode signature refusals (the same categorized cascade
            the direct-mode route surfaces).
        PipelexError: non-validation failures (config, library, tracing infra).
    """
    prev_library_id = get_current_library_id_or_none()
    # Failure → validate_bundle owns its teardown and the error propagates through the boundary.
    # Success → the library is left loaded + current (D6) and THIS activity owns the teardown.
    validate_result = await validate_bundle(
        mthds_contents=arg.mthds_contents,
        library_dirs=[Path(lib_dir) for lib_dir in arg.library_dirs] if arg.library_dirs is not None else None,
        allow_signatures=arg.allow_signatures,
    )
    library_id = get_current_library_id_or_none()
    try:
        # Graph: best-effort (D5), against the SAME loaded library.
        graph_spec: GraphSpec | None = None
        graph_pipe_ref = arg.pipe_code or _qualified_main_pipe(validate_result.blueprints)
        if graph_pipe_ref and library_id:
            main_pipe = get_required_pipe(pipe_code=graph_pipe_ref)
            try:
                graph_spec = await dry_run_pipe_in_process(pipe=main_pipe, library_id=library_id)
            except (DryRunError, PipeRunError, PipeRouterError, ValidationError, FactoryException) as graph_error:
                log.warning(
                    f"act_dry_validate: graph dry-run of '{graph_pipe_ref}' did not produce a graph "
                    f"({type(graph_error).__name__}); returning validation result without graph_spec"
                )

        return DryValidateResult(dry_run_outputs=validate_result.dry_run_result, graph_spec=graph_spec)
    finally:
        # Restore the caller's outer current-library FIRST so the guarantee survives a teardown
        # raise, then tear the validated library down once — mirrors acquire_and_validate.
        if prev_library_id is not None and prev_library_id != library_id:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        if library_id is not None:
            get_library_manager().teardown(library_id=library_id)


def _qualified_main_pipe(blueprints: list[PipelexBundleBlueprint]) -> str | None:
    """Return the domain-qualified main_pipe of the first blueprint declaring one, else None."""
    for blueprint in blueprints:
        if blueprint.main_pipe:
            return PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)
    return None
