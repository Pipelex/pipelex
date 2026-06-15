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

The activity result carries everything the canonical validation report needs that must be
computed worker-side, against the worker's loaded library (D10): the success-only status map,
the best-effort ``GraphSpec``, the library-wide ``pending_signatures``, and the
``pipe_io_contracts`` IO contracts (built inside the library window — their JSON-Schema rendering
needs the loaded library's class registry, so the API side never needs to re-acquire one).

Error contract (D3): validation failures (blueprint/factory/wiring errors, unexpected pipe failures,
strict-mode signature refusals) RAISE out of ``validate_bundle`` as ``ValidateBundleError`` and
cross the boundary as structured ``ErrorReport``s via ``convert_pipelex_errors`` — the API
renders them as the same RFC 7807 422 the direct path produces (identical ``error_type``,
``error_domain=input``, caller-facing message carrying the offending refs).

Graph best-effort (D5, widened to cross-backend parity): any ``PipelexError`` raised while
resolving or dry-running the graph pipe — plus pydantic ``ValidationError`` / polyfactory
``FactoryException`` (the mock-input mint shapes) — degrades to ``graph_spec=None``. This is
the exact contract the direct-mode route applies around ``dry_run_pipeline`` and the same
catch ``BundleValidator._classify_pipe`` uses, so both backends answer identically for the
same bundle. Only non-Pipelex programming bugs propagate and fail the activity, mirroring
``assemble_tracing``'s bug-propagation policy.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipe_run.dry_run_in_process import best_effort_graph_spec
from pipelex.pipeline.blueprint_selection import select_primary_blueprint
from pipelex.pipeline.bundle_validator import DryRunOutput
from pipelex.pipeline.pipe_io_contracts import PipeIOContract, build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


class DryValidateArg(BaseModel):
    """Input for the dry-run+validation activity (serializable across the Temporal boundary)."""

    mthds_contents: list[str] | None = None
    # Optional per-content logical names threaded onto `blueprint.source` so the worker's
    # categorized `ValidateBundleError` carries a real `source` (length must match
    # `mthds_contents` — `validate_bundle` enforces it). `None` keeps `source=None`.
    mthds_names: list[str] | None = None
    allow_signatures: bool = False
    # Optional explicit pipe selection for the graph arm; defaults to the bundle's declared
    # main_pipe (qualified from the first blueprint declaring one). The sweep always covers the
    # whole bundle; no graph is produced when neither this nor a main_pipe is set.
    pipe_code: str | None = None


class DryValidateResult(BaseModel):
    """Output of the dry-run+validation activity — everything the canonical validation report
    needs that must be computed worker-side, against the worker's loaded library (D10):

    - ``dry_run_outputs``: the success-only per-pipe status map (D3) that
      ``build_validated_pipes`` projects into ``validated_pipes``.
    - ``graph_spec``: the best-effort graph of the main pipe.
    - ``pending_signatures``: qualified refs of pipes still declared as ``PipeSignature`` in
      the assembled library — the runnability verdict's input.
    - ``pipe_io_contracts``: per-pipe IO contracts keyed by ``pipe_ref``, built via
      ``build_pipe_io_contracts`` inside the worker's library window (JSON-Schema rendering
      resolves bundle-defined structure classes through the loaded library's class registry,
      so the API side never needs to re-acquire a library).
    """

    dry_run_outputs: dict[str, DryRunOutput]
    graph_spec: GraphSpec | None = None
    # Deliberately REQUIRED (no wire default): a version-skewed worker that doesn't emit
    # these fields must fail loudly at deserialization, not default to "nothing pending"
    # and yield a silently wrong is_runnable verdict.
    pending_signatures: list[str]
    pipe_io_contracts: dict[str, PipeIOContract]


@activity.defn(name="act_dry_validate")
@convert_pipelex_errors
async def act_dry_validate(arg: DryValidateArg) -> DryValidateResult:
    """Run the validation sweep + the in-memory graph dry-run against one library, in-process.

    Raises (crossing as structured ``ErrorReport``s via ``convert_pipelex_errors``):
        ValidateBundleError: any validation failure — blueprint/factory/wiring errors, unexpected
            dry-run pipe failures, strict-mode signature refusals (the same categorized cascade
            the direct-mode route surfaces).
        PipeIOContractError: a JSON-Schema rendering failure while building `pipe_io_contracts`
            (non-retryable at the workflow tier, like ValidateBundleError — deterministic).
        PipelexError: non-validation failures (config, library, tracing infra).
    """
    prev_library_id = get_current_library_id_or_none()
    # Failure → validate_bundle owns its teardown and the error propagates through the boundary.
    # Success → the library is left loaded + current (D6) and THIS activity owns the teardown.
    validate_result = await validate_bundle(
        mthds_contents=arg.mthds_contents,
        mthds_names=arg.mthds_names,
        allow_signatures=arg.allow_signatures,
    )
    library_id = get_current_library_id_or_none()
    # Explicit body-success flag — NOT sys.exc_info() in the finally, which also sees an
    # exception the CALLER is currently handling and would wrongly suppress a genuine
    # teardown failure after a successful body.
    body_succeeded = False
    try:
        # Pipe IO contracts: built INSIDE the library window (D10) — the JSON-Schema rendering
        # resolves bundle-defined structure classes through the loaded library's class registry.
        pipe_io_contracts = build_pipe_io_contracts(validate_result.pipes)

        # Graph: best-effort (D5), against the SAME loaded library, via the ONE shared
        # graph-arm implementation — an unknown explicit pipe_code degrades to
        # graph_spec=None just like any other graph-arm domain failure.
        graph_spec: GraphSpec | None = await best_effort_graph_spec(
            pipe_ref=arg.pipe_code or select_primary_blueprint(validate_result.blueprints).main_pipe_ref,
            library_id=library_id,
            log_context="act_dry_validate",
        )

        result = DryValidateResult(
            dry_run_outputs=validate_result.dry_run_result,
            graph_spec=graph_spec,
            pending_signatures=validate_result.pending_signatures,
            pipe_io_contracts=pipe_io_contracts,
        )
        body_succeeded = True
        return result
    finally:
        # Restore the caller's outer current-library FIRST so the guarantee survives a teardown
        # raise, then tear the validated library down once — mirrors acquire_and_validate.
        if prev_library_id is not None and prev_library_id != library_id:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        if library_id is not None:
            try:
                get_library_manager().teardown(library_id=library_id)
            except PipelexError as teardown_error:
                # A teardown failure must not REPLACE the body's in-flight error (the caller's
                # 422 would name the teardown instead of the user's actual problem) — suppress
                # it and let the primary propagate; raise it only when the body succeeded.
                # Mirrors PipeRun.run's close_tracer handling.
                if body_succeeded:
                    raise
                log.error(
                    f"act_dry_validate: library teardown also failed after a body error; "
                    f"raising the original error. Suppressed teardown error: {teardown_error}"
                )
