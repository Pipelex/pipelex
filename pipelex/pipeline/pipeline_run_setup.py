from pathlib import Path
from typing import TYPE_CHECKING

from pipelex import log
from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import (
    get_library_manager,
    get_otel_tracer,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
    get_telemetry_manager,
    resolve_library_dirs,
    set_current_library,
    teardown_current_library,
)
from pipelex.pipe_run.dry_run import convert_to_working_memory_format
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import (
    FORCE_DRY_RUN_MODE_ENV_KEY,
    VariableMultiplicity,
)
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.exceptions import PipeExecutionError
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.pipeline.job_metadata import JobMetadata, OtelContext
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.otel_factory import OtelFactory

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.core.pipes.pipe_abstract import PipeAbstract
    from pipelex.graph.graph_context import GraphContext


async def pipeline_run_setup(
    execution_config: PipelineExecutionConfig,
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    plx_content: str | None = None,
    bundle_uri: str | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domain_codes: list[str] | None = None,
    user_id: str | None = None,
) -> tuple[PipeJob, str, str]:
    """Set up a pipeline for execution.

    This function handles all the common setup logic for both ``execute_pipeline``
    and ``start_pipeline``, including library setup, pipe loading, working memory
    initialization, and pipe job creation.

    Parameters
    ----------
    execution_config:
        Pipeline execution configuration including graph tracing settings.
        Must be provided by the caller (typically resolved at the entry point).
    library_id:
        Unique identifier for the library instance. If not provided, defaults to the
        auto-generated ``pipeline_run_id``. Use a custom ID when you need to manage
        multiple library instances or maintain library state across executions.
    library_dirs:
        List of directory paths to load pipe definitions from. Combined with directories
        from the ``PIPELEXPATH`` environment variable (PIPELEXPATH directories are searched
        first). When provided alongside ``plx_content``, definitions from both sources
        are loaded into the library.
    pipe_code:
        Code identifying the pipe to execute. Required when ``plx_content`` is not
        provided. When both ``plx_content`` and ``pipe_code`` are provided, the
        specified pipe from the PLX content will be executed (overriding any
        ``main_pipe`` defined in the content).
    plx_content:
        Complete PLX file content as a string. The pipe to execute is determined by
        ``pipe_code`` (if provided) or the ``main_pipe`` property in the PLX content.
        Can be combined with ``library_dirs`` to load additional definitions.
    bundle_uri:
        URI identifying the bundle. Used to detect if the bundle was already loaded
        from library directories (e.g., via PIPELEXPATH) to avoid duplicate domain
        registration. If provided and the resolved absolute path is already in the
        loaded PLX paths, the ``plx_content`` loading will be skipped.
    inputs:
        Inputs passed to the pipeline. Can be either a ``PipelineInputs`` dictionary
        or a ``WorkingMemory`` instance.
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity specification.
    dynamic_output_concept_code:
        Override the dynamic output concept code.
    pipe_run_mode:
        Pipe run mode: ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``. If not specified,
        inferred from the environment variable ``PIPELEX_FORCE_DRY_RUN_MODE``. Defaults
        to ``PipeRunMode.LIVE`` if the environment variable is not set.
    search_domain_codes:
        List of domain codes to search for pipes. The executed pipe's domain is automatically
        added if not already present.
    user_id:
        Unique identifier for the user (optional).

    Returns:
    -------
    tuple[PipeJob, str, str]
        A tuple containing the pipe job ready for execution, the pipeline run ID,
        and the library ID.

    """
    user_id = user_id or OTelConstants.DEFAULT_USER_ID
    if not plx_content and not pipe_code:
        msg = "Either pipe_code or plx_content must be provided to the pipeline API."
        raise ValueError(msg)

    pipeline = get_pipeline_manager().add_new_pipeline(pipe_code=pipe_code)
    pipeline_run_id = pipeline.pipeline_run_id

    if not library_id:
        library_id = pipeline_run_id

    library_manager = get_library_manager()
    set_current_library(library_id=library_id)
    library_manager.open_library(library_id=library_id)

    pipe: PipeAbstract | None = None
    blueprint: PipelexBundleBlueprint | None = None

    effective_dirs, source_label = resolve_library_dirs(library_dirs)

    if effective_dirs:
        log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}):")
        for index_dir, dir_path in enumerate(effective_dirs):
            log.verbose(f"  [{index_dir + 1}] {dir_path}")
        library_manager.load_libraries(
            library_id=library_id,
            library_dirs=effective_dirs,
        )
    else:
        log.verbose(f"No library directories to load ({source_label})")

    # Then handle plx_content or pipe_code
    if plx_content:
        validate_bundle_result = await validate_bundle(plx_content=plx_content)

        # Check if this bundle was already loaded from library directories
        bundle_already_loaded = False
        if bundle_uri:
            try:
                resolved_bundle_uri = str(Path(bundle_uri).resolve())
            except (OSError, RuntimeError):
                # Use str(Path(...)) to normalize the path (e.g., "./file.plx" -> "file.plx")
                # to match the normalization done in library_manager._load_plx_files_into_library
                resolved_bundle_uri = str(Path(bundle_uri))
            current_library = library_manager.get_library(library_id=library_id)
            bundle_already_loaded = resolved_bundle_uri in current_library.loaded_plx_paths
            if bundle_already_loaded:
                log.verbose(f"Bundle '{bundle_uri}' already loaded from library directories, skipping duplicate load")

        if not bundle_already_loaded:
            library_manager.load_from_blueprints(library_id=library_id, blueprints=validate_bundle_result.blueprints)

        # For now, we only support one blueprint when given a plx_content. So blueprints is of length 1.
        blueprint = validate_bundle_result.blueprints[0]
        if pipe_code:
            pipe = get_required_pipe(pipe_code=pipe_code)
        elif blueprint.main_pipe:
            pipe = get_required_pipe(pipe_code=blueprint.main_pipe)
        else:
            msg = "No pipe code or main pipe in the PLX content provided to the pipeline API."
            raise PipeExecutionError(message=msg)
    elif pipe_code:
        pipe = get_required_pipe(pipe_code=pipe_code)
    else:
        msg = "Either provide pipe_code or plx_content to the pipeline API. 'pipe_code' must be provided when 'plx_content' is None"
        raise PipeExecutionError(message=msg)

    pipe_code = pipe.code

    search_domain_codes = search_domain_codes or []
    if pipe.domain_code not in search_domain_codes:
        search_domain_codes.insert(0, pipe.domain_code)

    # Initialize graph tracing if requested (after pipe is loaded so we have domain info)
    graph_context: GraphContext | None = None
    if execution_config.is_generate_graph:
        graph_tracer_manager = GraphTracerManager.get_or_create_instance()
        graph_context = graph_tracer_manager.open_tracer(
            graph_id=pipeline_run_id,
            data_inclusion=execution_config.graph_config.data_inclusion,
            pipeline_ref_domain=pipe.domain_code,
            pipeline_ref_main_pipe=pipe_code,
        )

    try:
        working_memory: WorkingMemory | None = None

        # First, process user-provided inputs
        if inputs:
            if isinstance(inputs, WorkingMemory):
                working_memory = inputs
            else:
                working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                    pipeline_inputs=inputs,
                    search_domain_codes=search_domain_codes,
                )

        # If mock inputs is enabled, generate mock data for missing required inputs
        if execution_config.is_mock_inputs:
            needed_inputs_spec = pipe.needed_inputs()
            needed_inputs_for_factory = convert_to_working_memory_format(needed_inputs_spec)

            # Filter out inputs that were already provided by the user
            if working_memory:
                provided_names = set(working_memory.root.keys())
                missing_inputs = [spec for spec in needed_inputs_for_factory if spec.variable_name not in provided_names]
            else:
                missing_inputs = needed_inputs_for_factory
                working_memory = WorkingMemoryFactory.make_empty()

            # Generate mock data only for missing inputs
            if missing_inputs:
                mock_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=missing_inputs)
                for name, stuff in mock_memory.root.items():
                    working_memory.add_new_stuff(name=name, stuff=stuff)

        # Normalize data URLs to pipelex-storage:// URIs if configured
        if working_memory and execution_config.is_normalize_data_urls_to_storage:
            working_memory = await normalize_data_urls_to_storage(working_memory)

        # TODO: rethink this, it's not forcing
        if pipe_run_mode is None:
            if run_mode_from_env := get_optional_env(key=FORCE_DRY_RUN_MODE_ENV_KEY):
                pipe_run_mode = PipeRunMode(run_mode_from_env)
            else:
                pipe_run_mode = PipeRunMode.LIVE

        get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)

        # Initialize OtelContext if telemetry is enabled (not dry mode and tracer available)
        # The trace_id is computed once here; span_id uses OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID for root
        otel_context: OtelContext | None = None
        if pipe_run_mode.is_live and get_otel_tracer() is not None:
            trace_id = OtelFactory.make_trace_id(pipeline_run_id=pipeline_run_id)
            trace_name, trace_name_redacted = OtelFactory.make_trace_names(pipeline_run_id=pipeline_run_id, pipe_code=pipe_code)
            otel_context = OtelContext(
                trace_id=trace_id,
                trace_name=trace_name,
                trace_name_redacted=trace_name_redacted,
                span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
            )
            # Emit trace start event immediately to establish trace name in PostHog
            # This must happen before any pipe spans are created/exported
            get_telemetry_manager().handle_trace_start(trace_name=trace_name, trace_name_redacted=trace_name_redacted, trace_id=trace_id)

        job_metadata = JobMetadata(
            user_id=user_id,
            pipeline_run_id=pipeline.pipeline_run_id,
            otel_context=otel_context,
            graph_context=graph_context,
        )

        pipe_run_params = PipeRunParamsFactory.make_run_params(
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
            pipe_run_mode=pipe_run_mode,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=pipe_run_params,
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name=output_name,
        )

        properties = {
            EventProperty.PIPELINE_RUN_ID: job_metadata.pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe.pipe_type,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_EXECUTE, properties=properties)

        return pipe_job, pipeline_run_id, library_id
    except Exception:
        # Cleanup graph tracer if it was opened
        if graph_context is not None:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                tracer_manager.close_tracer(pipeline_run_id)
        # Cleanup library
        library_manager.teardown(library_id=library_id)
        teardown_current_library()
        raise
