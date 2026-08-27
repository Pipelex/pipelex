"""In-process orchestration for the protocol `validate` operation.

`validate_bundles_in_process` is the single in-process implementation of `validate`,
shared by every Pipelex backend that runs the sweep locally: the local runtime
(`PipelexMTHDSProtocol.validate`) and the hosted API's direct (non-Temporal) path
(`ApiRunner.validate`). Keeping it in one place means the load-bearing library-window
management — `validate_bundle` leaves its validation library OPEN on success, and this
long-lived entry point must restore the caller's current-library and tear the validation
library down — lives once, so the two backends cannot drift on teardown semantics.

The `mthds_sources` parameter is the in-memory source-threading hook: the API submits
sourceless bundle text (`mthds_contents: list[str]`), so without per-content sources
`blueprint.source` is `None` and cross-file diagnostics misfire. Threading sources here lands
them on `blueprint.source` for both the success path and the categorized
`ValidateBundleError` (whose per-error `source` the extension maps to the owning file). The
local protocol runtime passes `None` — its `validate` interface carries only sourceless
content strings, so `blueprint.source` stays `None` on that path too. (The CLI populates
`source` from the real file path via a separate `validate_bundle(mthds_file_path=…)` entry
point that bypasses this orchestrator.)
"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex import log
from pipelex.base_exceptions import PipelexError, ValidationErrorItem
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipe_run.dry_run_in_process import best_effort_graph_spec
from pipelex.pipeline.advisory_warnings import build_advisory_warnings
from pipelex.pipeline.blueprint_selection import collect_entry_pipe_refs, select_primary_blueprint
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.input_form import InputForm, build_input_form, qualify_current_library_crate
from pipelex.pipeline.liftable_pipes import LiftablePipeEntry, build_liftable_pipes
from pipelex.pipeline.pipe_io_contracts import PipeIOContracts, build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_report import PipelexValidationReport, build_validation_report

if TYPE_CHECKING:
    from pipelex.graph.graphspec import GraphSpec


async def validate_bundles_in_process(
    *,
    mthds_contents: list[str],
    mthds_sources: list[str] | None = None,
    library_dirs: Sequence[Path] | None = None,
    allow_signatures: bool = False,
    graph_pipe_code: str | None = None,
    log_context: str = "validate",
) -> PipelexValidationReport:
    """Parse, validate, and dry-run MTHDS bundles in-process; assemble the canonical report.

    Wraps `validate_bundle` and assembles its result into the canonical
    `PipelexValidationReport` via `build_validation_report`: the primary
    `bundle_blueprint`, `pipe_io_contracts` keyed by namespaced `pipe_ref`, the per-pipe
    `validated_pipes` sweep outcomes, and the runnability verdict — `pending_signatures`
    plus `is_runnable = not pending_signatures`. `graph_spec` is best-effort: when the batch
    declares a `main_pipe` it is dry-run in-process against the validation library; a
    graph-arm domain failure degrades to `graph_spec=None` with validation still successful.

    Args:
        mthds_contents: MTHDS contents to load (always a list, even for one file).
        mthds_sources: Optional per-content sources threaded onto `blueprint.source`
            (length must match `mthds_contents` — `validate_bundle` enforces it). `None`
            for the local protocol runtime, which receives only sourceless content strings
            (so `source` stays `None` on that path).
        library_dirs: Resolved library directories to load before the bundle.
        allow_signatures: Tolerate unimplemented pipe signatures (strict by default).
        graph_pipe_code: Optional explicit pipe target for the best-effort graph arm.
            When omitted, the graph arm keeps the existing default of targeting the
            selected bundle `main_pipe`. Bare and qualified refs are accepted according
            to the loaded pipe library's normal resolution rules.
        log_context: Label used in graph-arm degradation and teardown-failure logs.

    Returns:
        PipelexValidationReport with the structural artifacts of a valid bundle.

    Raises:
        PipelexError: When the bundle is invalid (parse, static validation, or dry-run failure).
    """
    # `validate_bundle` deliberately leaves its validation library OPEN and current on
    # success (the CLI surfaces consume it before process exit). This entry point is
    # long-lived, so restore the caller's current-library and tear the validation library
    # down on the way out — on failure `validate_bundle` already did both, so
    # `validation_library_id` stays None and the cleanup below is a no-op. Artifacts that
    # need the open validation library are built INSIDE the window, before the `finally`
    # tears it down: `pipe_io_contracts`'s JSON-Schema rendering resolves bundle-defined
    # structure classes through the class registry, `input_form`'s class-backed reflection
    # reads the same registry, and the graph arm dry-runs the main pipe against the loaded
    # library.
    prev_library_id = get_current_library_id_or_none()
    validation_library_id: str | None = None
    # Explicit body-success flag — NOT sys.exc_info() in the finally, which also sees an
    # exception the CALLER is currently handling (validate awaited inside an except block)
    # and would wrongly suppress a genuine teardown failure after a successful body.
    body_succeeded = False
    try:
        result = await validate_bundle(
            mthds_contents=mthds_contents,
            mthds_sources=mthds_sources,
            library_dirs=library_dirs,
            allow_signatures=allow_signatures,
        )
        # Capture the validation library id ONCE, right after validate_bundle leaves it
        # current — the graph arm and the finally must target the SAME library even if
        # something inside the window later moves the contextvar.
        validation_library_id = get_current_library_id_or_none()
        pipe_io_contracts: PipeIOContracts = build_pipe_io_contracts(result.pipes)
        # One crate qualification per validate pass — the descriptors and the hint lint read the same one.
        qualified_crate = qualify_current_library_crate()
        input_form: InputForm = build_input_form(result.pipes, qualified_crate=qualified_crate)
        # One taint walk per validate pass — both report projections read the same analyses.
        taint_analyses = collect_controller_taint_analyses(result.pipes)
        liftable_pipes: list[LiftablePipeEntry] = build_liftable_pipes(taint_analyses)
        warnings: list[ValidationErrorItem] = build_advisory_warnings(
            taint_analyses=taint_analyses,
            input_form=input_form,
            entry_pipe_refs=collect_entry_pipe_refs(result.blueprints),
            qualified_crate=qualified_crate,
        )
        graph_target_ref = graph_pipe_code if graph_pipe_code is not None else select_primary_blueprint(result.blueprints).main_pipe_ref
        graph_spec: GraphSpec | None = await best_effort_graph_spec(
            pipe_ref=graph_target_ref,
            library_id=validation_library_id,
            log_context=log_context,
        )
        body_succeeded = True
    finally:
        if validation_library_id is not None and validation_library_id != prev_library_id:
            # Restore the caller's outer current-library FIRST so the guarantee survives a
            # teardown raise — mirrors act_dry_validate.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            try:
                get_library_manager().teardown(library_id=validation_library_id)
            except PipelexError as teardown_error:
                # A teardown failure must not REPLACE the body's in-flight error (the
                # caller's error would name the teardown instead of the actual problem) —
                # suppress it and let the primary propagate; raise it only when the body
                # succeeded. Mirrors act_dry_validate's finally.
                if body_succeeded:
                    raise
                log.error(
                    f"{log_context}: library teardown also failed after a body error; "
                    f"raising the original error. Suppressed teardown error: {teardown_error}"
                )
    return build_validation_report(
        blueprints=result.blueprints,
        pipe_io_contracts=pipe_io_contracts,
        input_form=input_form,
        liftable_pipes=liftable_pipes,
        dry_run_result=result.dry_run_result,
        pending_signatures=result.pending_signatures,
        graph_spec=graph_spec,
        warnings=warnings,
    )
