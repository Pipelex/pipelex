"""Reusable execution seams factored out of ``pipeline_run_setup`` (D2).

Two pure-ish building blocks composed by both the single-run wrapper
(``pipeline_run_setup``) and the batch validation service
(``BundleValidator``, Phase 2):

- :func:`acquire_library` — set the current library, open it, and load
  directories + blueprints into it. Owns its own load-failure teardown (open,
  then load under a ``try``; on failure restore the caller's outer
  current-library and tear the just-opened library down). Returns the
  ``library_id`` plus the bundle's qualified ``main_pipe`` (when an
  ``mthds_contents`` bundle declares one), leaving pipe resolution to the
  caller.
- :func:`prepare_pipe_job` — build a :class:`PipeJob` against an already-open
  library: working memory (user inputs, mock inputs, data-url normalization),
  run params, job metadata, and the library crate. **Pure**: no pipeline-manager
  registration, no report-registry open, no telemetry, no graph-tracer open, no
  library mutation.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from mthds.protocol.pipeline_inputs import PipelineInputs

from pipelex import log
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.kernel.memory_ops import shape_inputs
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import VariableMultiplicity
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.blueprint_selection import select_primary_blueprint
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import validate_storage_scope
from pipelex.tools.misc.file_utils import reject_bare_str_or_path

if TYPE_CHECKING:
    from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.system.trace_context import TraceContext


def acquire_library(
    library_id: str,
    *,
    library_dirs: list[str] | None = None,
    mthds_contents: list[str] | None = None,
    bundle_uris: list[str] | None = None,
) -> tuple[str, str | None]:
    """Set the current library, open it, and load dirs + blueprints into it.

    Owns its own load-failure teardown: open then load under a ``try``; on any
    failure (including ``BaseException`` such as ``asyncio.CancelledError``),
    restore the caller's outer current-library and tear the just-opened library
    down before re-raising — so a failed load never leaks a ``Library``. On
    success the library is left open and current for the caller to use.

    Returns the ``library_id`` and the bundle's qualified ``main_pipe`` ref
    (``domain.pipe_code``) when an ``mthds_contents`` bundle declares one, else
    ``None``. Pipe resolution is the caller's responsibility.
    """
    library_manager = get_library_manager()
    prev_library_id = get_current_library_id_or_none()
    # Adopt the canonical id open_library keyed the Library under: when given a falsy library_id it
    # generates a fresh uuid. Returning/tearing down the passed-in id instead would, for library_id="",
    # route teardown("") past LibraryManager.teardown's `if library_id:` guard and tear down ALL libraries.
    library_id, _ = library_manager.open_library(library_id=library_id)
    success = False
    try:
        set_current_library(library_id=library_id)

        effective_dirs, source_label = resolve_library_dirs(library_dirs)
        if effective_dirs:
            log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}):")
            for index_dir, dir_path in enumerate(effective_dirs):
                log.verbose(f"  [{index_dir + 1}] {dir_path}")
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)
        else:
            log.verbose(f"No library directories to load ({source_label})")

        qualified_main_pipe: str | None = None
        if mthds_contents:
            all_blueprints = [MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]

            # Filter out blueprints whose URIs are already loaded (e.g. via PIPELEXPATH).
            blueprints_to_load: list[PipelexBundleBlueprint] = list(all_blueprints)
            if bundle_uris:
                current_library = library_manager.get_library(library_id=library_id)
                blueprints_to_load = []
                for blueprint, uri in zip(all_blueprints, bundle_uris, strict=True):
                    try:
                        resolved_uri = Path(uri).resolve()
                    except (OSError, RuntimeError):
                        resolved_uri = Path(uri)
                    if resolved_uri in current_library.loaded_mthds_paths:
                        log.verbose(f"Bundle '{uri}' already loaded from library directories, skipping")
                    else:
                        blueprints_to_load.append(blueprint)

            if blueprints_to_load:
                library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints_to_load)

            # Qualify main_pipe with domain to avoid ambiguity when multiple domains define pipes with
            # the same code — via the one shared selection rule (first declaring main_pipe, else first).
            qualified_main_pipe = select_primary_blueprint(all_blueprints).main_pipe_ref

        success = True
        return library_id, qualified_main_pipe
    finally:
        if not success:
            # Restore the caller's outer current-library FIRST so the safety guarantee holds even when
            # teardown raises; route the "no outer was set" case through clear_current_library.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)


def load_libraries_and_activate(library_dirs: Sequence[str | Path] | None = None) -> str:
    """Open a fresh library, set it current, resolve + load ``library_dirs``, and leave it loaded.

    The single public entry for the open/set/load ceremony that ``Pipelex.make`` deliberately does
    **not** perform (``make`` only records default dirs). Returns the new ``library_id``; the library
    stays open and current for the caller to query or sweep (e.g. via
    :meth:`BundleValidator.validate_current_library`). Delegates to :func:`acquire_library` for the
    tested open + set-current + load + load-failure teardown, dropping the bundle ``main_pipe`` element
    that directory-loading callers do not need.

    ``library_dirs`` follows the standard 3-tier resolution (see :func:`resolve_library_dirs`): ``None``
    falls back to the instance defaults / ``PIPELEXPATH``; an explicit ``[]`` disables loading. A bare
    ``str``/``Path`` (a single directory) is rejected — wrap it in a list.
    """
    reject_bare_str_or_path(library_dirs, param_name="library_dirs")
    library_id, _ = acquire_library(
        library_id="",
        library_dirs=[str(lib_dir) for lib_dir in library_dirs] if library_dirs is not None else None,
    )
    return library_id


async def prepare_pipe_job(
    pipe: PipeAbstract,
    *,
    library_id: str,
    execution_config: PipelineExecutionConfig,
    pipe_run_mode: PipeRunMode,
    pipeline_run_id: str,
    user_id: str,
    storage_scope: str,
    inputs: PipelineInputs | WorkingMemory | None = None,
    search_scope: str | None = None,
    trace_context: "TraceContext | None" = None,
    otel_context: OtelContext | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_ref: str | None = None,
    request_id: str | None = None,
    is_mock_usage: bool = False,
    inputs_base_dir: Path | None = None,
) -> PipeJob:
    """Build a :class:`PipeJob` for ``pipe`` against an already-open library.

    Pure: assembles working memory (user inputs, mock inputs when
    ``execution_config.is_mock_inputs``, optional data-url normalization), run
    params, job metadata, and the library crate. Performs no pipeline-manager
    registration, no report-registry open, no telemetry, no graph-tracer open,
    and no library mutation. ``trace_context`` / ``otel_context`` are created by
    the caller and threaded onto the job metadata. ``is_mock_usage`` is the single-writer
    point onto :attr:`CogtRunParams.is_mock_usage` — the internal DRY sub-flag that makes the
    dry LLM leaves report non-zero synthetic usage so the cost report renders (DRY-only;
    rejected on a LIVE run).

    A keyless boot (``Pipelex.make(needs_inference=False)``) forces the run to DRY (eng review
    D4): the backend still dispatches normally and the cogt leaf mocks, so a keyless Temporal
    submitter exercises the real distribution machinery at zero spend. The flag is resolved by
    ``PipeRunParamsFactory.make_run_params`` (the single writer of ``run_mode``), so it covers
    every entry point that builds run params, not just this one.
    """
    # Validate the scope HERE, before anything composes a storage key from it.
    #
    # `JobMetadata` validates it too, and that is where the invariant is
    # documented — but it is constructed BELOW the data-url normalization, which
    # writes `{storage_scope}/assets/...` to real storage. So an unvalidated
    # scope carrying `..` reached the storage provider and escaped the tenant,
    # and the validator that was supposed to prevent it ran afterwards on a
    # value whose damage was already done. Ordering, not absence, was the defect.
    #
    # This is deliberately not a "second gate": it is the FIRST one on this path.
    storage_scope = validate_storage_scope(value=storage_scope)

    working_memory: WorkingMemory | None = None

    # First, process user-provided inputs. Empty PipelineInputs is falsy and behaves like no inputs.
    if inputs:
        if isinstance(inputs, WorkingMemory):
            working_memory = inputs
        else:
            # Thread the pipe's declared inputs so each value is shaped top-down against the
            # signature (Smart Inputs). `pipe.inputs` is the method-boundary contract — the same
            # source the Optionals pass reads below — not the aggregated `needed_inputs()`. Through
            # the kernel op so the interpreter and a programmatic caller shape inputs identically.
            working_memory = shape_inputs(
                inputs=inputs,
                concept_provider=get_concept_library(),
                input_specs=pipe.inputs,
                search_scope=search_scope,
                inputs_base_dir=inputs_base_dir,
            )

    # If mock inputs is enabled, generate mock data for missing required inputs.
    if execution_config.is_mock_inputs:
        needed_inputs_spec = pipe.needed_inputs()
        needed_inputs_for_factory = WorkingMemoryFactory.convert_to_working_memory_format(needed_inputs_spec=needed_inputs_spec)

        # Filter out inputs that were already provided by the user.
        if working_memory:
            provided_names = set(working_memory.root.keys())
            missing_inputs = [spec for spec in needed_inputs_for_factory if spec.variable_name not in provided_names]
        else:
            missing_inputs = needed_inputs_for_factory
            working_memory = WorkingMemoryFactory.make_empty()

        if missing_inputs:
            mock_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=missing_inputs)
            for name, stuff in mock_memory.root.items():
                working_memory.add_new_stuff(name=name, stuff=stuff)

    # Optional method inputs (D5): each declared-optional input the caller omitted starts as a
    # recorded not-provided absence instead of a bare missing key. Runs after mock filling so the
    # dry-run sweep stays all-present (D6) — a mocked optional slot gets no record. The marker is
    # read from the pipe's OWN declared inputs — the method-boundary contract — not from
    # ``needed_inputs()``, whose aggregation carries a controller's children markers.
    omitted_optional_specs = [
        named_stuff_spec
        for named_stuff_spec in pipe.inputs.named_stuff_specs
        if named_stuff_spec.presence.is_optional
        and (
            working_memory is None
            or (
                working_memory.get_optional_stuff(named_stuff_spec.variable_name) is None
                # A slot already resolved as a recorded absence was NOT omitted — re-recording
                # would downgrade its provenance to a fresh not-provided.
                and working_memory.get_optional_absence(named_stuff_spec.variable_name) is None
            )
        )
    ]
    if omitted_optional_specs:
        if working_memory is None:
            working_memory = WorkingMemoryFactory.make_empty()
        for named_stuff_spec in omitted_optional_specs:
            working_memory.record_absence(
                AbsenceRecord(
                    variable_name=named_stuff_spec.variable_name,
                    kind=AbsenceKind.NOT_PROVIDED,
                    reason=f"optional input '{named_stuff_spec.variable_name}' was not provided by the caller",
                )
            )

    # Normalize data URLs to pipelex-storage:// URIs if configured.
    if working_memory and execution_config.is_normalize_data_urls_to_storage and not execution_config.is_mock_inputs:
        working_memory = await normalize_data_urls_to_storage(working_memory, storage_scope=storage_scope)

    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id=user_id, storage_scope=storage_scope, pipeline_run_id=pipeline_run_id, request_id=request_id),
        otel_context=otel_context,
        trace_context=trace_context,
    )

    pipe_run_params = PipeRunParamsFactory.make_run_params(
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        pipe_run_mode=pipe_run_mode,
        is_mock_usage=is_mock_usage,
    )

    # Build the library crate from all accumulated blueprints for Temporal dispatch.
    library_crate = get_library_manager().get_crate(library_id=library_id)

    return PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=output_name,
        library_crate=library_crate,
    )
