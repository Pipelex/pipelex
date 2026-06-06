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

from mthds.models.pipeline_inputs import PipelineInputs

from pipelex import log
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import VariableMultiplicity
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.pipeline.job_metadata import JobMetadata, OtelContext
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.tools.misc.file_utils import reject_bare_str_or_path

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.graph.graph_context import GraphContext


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
            all_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]

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

            # Qualify main_pipe with domain to avoid ambiguity when multiple domains define pipes with the
            # same code. main_pipe is validated as snake_case (no dots), so it is always a bare code.
            for blueprint in all_blueprints:
                if blueprint.main_pipe:
                    qualified_main_pipe = PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)
                    break

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
    inputs: PipelineInputs | WorkingMemory | None = None,
    search_domain_codes: list[str] | None = None,
    graph_context: "GraphContext | None" = None,
    otel_context: OtelContext | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_ref: str | None = None,
    request_id: str | None = None,
    is_mock_inference: bool = False,
) -> PipeJob:
    """Build a :class:`PipeJob` for ``pipe`` against an already-open library.

    Pure: assembles working memory (user inputs, mock inputs when
    ``execution_config.is_mock_inputs``, optional data-url normalization), run
    params, job metadata, and the library crate. Performs no pipeline-manager
    registration, no report-registry open, no telemetry, no graph-tracer open,
    and no library mutation. ``graph_context`` / ``otel_context`` are created by
    the caller and threaded onto the job metadata. ``is_mock_inference`` (the
    ``--mock-inference`` trigger) is the single-writer point onto
    :attr:`JobMetadata.is_mock_inference` — a LIVE run whose LLM cogt leaf calls are
    faked (non-LLM leaves — image-gen / extract / search — raise ``MockInferenceUnsupportedError``).
    """
    working_memory: WorkingMemory | None = None

    # First, process user-provided inputs. Empty PipelineInputs is falsy and behaves like no inputs.
    if inputs:
        if isinstance(inputs, WorkingMemory):
            working_memory = inputs
        else:
            working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                pipeline_inputs=inputs,
                search_domain_codes=search_domain_codes,
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

    # Normalize data URLs to pipelex-storage:// URIs if configured.
    if working_memory and execution_config.is_normalize_data_urls_to_storage and not execution_config.is_mock_inputs:
        working_memory = await normalize_data_urls_to_storage(working_memory)

    job_metadata = JobMetadata(
        user_id=user_id,
        pipeline_run_id=pipeline_run_id,
        otel_context=otel_context,
        graph_context=graph_context,
        request_id=request_id,
        is_mock_inference=is_mock_inference,
    )

    pipe_run_params = PipeRunParamsFactory.make_run_params(
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        pipe_run_mode=pipe_run_mode,
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
