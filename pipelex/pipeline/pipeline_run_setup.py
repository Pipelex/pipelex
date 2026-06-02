from typing import TYPE_CHECKING

from mthds.models.pipeline_inputs import PipelineInputs

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_otel_tracer,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
    get_telemetry_manager,
    set_current_library,
)
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import (
    FORCE_DRY_RUN_MODE_ENV_KEY,
    VariableMultiplicity,
)
from pipelex.pipeline.exceptions import PipeExecutionError
from pipelex.pipeline.execution_seams import acquire_library, prepare_pipe_job
from pipelex.pipeline.job_metadata import OtelContext
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.tracing.event_log_factory import make_event_log

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract
    from pipelex.graph.graph_context import GraphContext
    from pipelex.tracing.event_log_protocol import EventLogProtocol


async def pipeline_run_setup(
    execution_config: PipelineExecutionConfig,
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    mthds_contents: list[str] | None = None,
    bundle_uris: list[str] | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_ref: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domain_codes: list[str] | None = None,
    user_id: str | None = None,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
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
        first). When provided alongside ``mthds_contents``, definitions from both sources
        are loaded into the library.
    pipe_code:
        Code identifying the pipe to execute. Required when ``mthds_contents`` is not
        provided. When both ``mthds_contents`` and ``pipe_code`` are provided, the
        specified pipe from the MTHDS contents will be executed (overriding any
        ``main_pipe`` defined in the contents).
    mthds_contents:
        List of MTHDS file contents as strings. The pipe to execute is determined by
        ``pipe_code`` (if provided) or the ``main_pipe`` property in the first content
        that declares one. Can be combined with ``library_dirs`` to load additional
        definitions.
    bundle_uris:
        List of URIs identifying the bundles. Used to detect if bundles were already
        loaded from library directories (e.g., via PIPELEXPATH) to avoid duplicate
        domain registration. If all resolved absolute paths are already in the loaded
        MTHDS paths, the ``mthds_contents`` loading will be skipped.
    inputs:
        Inputs passed to the pipeline. Can be either a ``PipelineInputs`` dictionary
        or a ``WorkingMemory`` instance.
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity specification.
    dynamic_output_concept_ref:
        Override the dynamic output concept ref.
    pipe_run_mode:
        Pipe run mode: ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``. If not specified,
        inferred from the environment variable ``PIPELEX_FORCE_DRY_RUN_MODE``. Defaults
        to ``PipeRunMode.LIVE`` if the environment variable is not set.
    search_domain_codes:
        List of domain codes to search for pipes. The executed pipe's domain is automatically
        added if not already present.
    user_id:
        Unique identifier for the user (optional).
    pipeline_run_id:
        Pre-generated pipeline run ID. If provided, this ID is used instead of
        generating a new one. Use this when the run record has already been created
        externally (e.g., by an API Gateway).
    request_id:
        Optional inbound ``X-Request-ID`` from the dispatcher (the value the
        external HTTP caller can use to correlate every log line and every
        ``ErrorReport`` back to its originating request). Threaded onto
        :class:`pipelex.pipeline.job_metadata.JobMetadata.request_id` so it
        crosses the Temporal serialization boundary intact.

    Returns:
    -------
    tuple[PipeJob, str, str]
        A tuple containing the pipe job ready for execution, the pipeline run ID,
        and the library ID.

    """
    user_id = user_id or OTelConstants.DEFAULT_USER_ID
    if not mthds_contents and not pipe_code:
        msg = "Either pipe_code or mthds_contents must be provided to the pipeline API."
        raise ValueError(msg)

    pipeline = get_pipeline_manager().add_new_pipeline(pipe_code=pipe_code, pipeline_run_id=pipeline_run_id)
    pipeline_run_id = pipeline.pipeline_run_id

    if not library_id:
        library_id = pipeline_run_id

    # Capture the caller's outer current-library before acquire_library overwrites it with the new id,
    # so a post-acquire failure can restore it instead of clobbering it (mirrors validate_bundle and
    # acquire_library's own load-failure teardown).
    prev_library_id = get_current_library_id_or_none()

    # Seam 1: open the library and load dirs + blueprints. Owns its own load-failure teardown.
    library_id, qualified_main_pipe = acquire_library(
        library_id=library_id,
        library_dirs=library_dirs,
        mthds_contents=mthds_contents,
        bundle_uris=bundle_uris,
    )

    library_manager = get_library_manager()
    graph_context: GraphContext | None = None
    event_log: EventLogProtocol | None = None
    registry_opened = False
    success = False
    try:
        # Resolve the pipe to execute against the now-open library.
        pipe: PipeAbstract
        if mthds_contents:
            if pipe_code:
                pipe = get_required_pipe(pipe_code=pipe_code)
            elif qualified_main_pipe:
                # main_pipe is validated as snake_case (no dots), so acquire_library returns it already
                # domain-qualified. See PipelexBundleBlueprint.validate_main_pipe_syntax.
                pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            else:
                msg = "No pipe_code provided and no main_pipe found in any of the MTHDS contents."
                raise PipeExecutionError(message=msg)
        elif pipe_code:
            pipe = get_required_pipe(pipe_code=pipe_code)
        else:
            msg = "Either provide pipe_code or mthds_contents to the pipeline API."
            raise PipeExecutionError(message=msg)

        pipe_code = pipe.code

        search_domain_codes = search_domain_codes or []
        if pipe.domain_code not in search_domain_codes:
            search_domain_codes.insert(0, pipe.domain_code)

        # Initialize graph tracing if requested (after pipe is loaded so we have domain info)
        if execution_config.is_generate_graph:
            # Create event log when tracing is enabled
            config = get_config()
            tracing_config = config.pipelex.tracing_config
            if tracing_config.is_enabled:
                event_log = make_event_log(tracing_config)

            graph_tracer_manager = GraphTracerManager.get_or_create_instance()
            graph_context = graph_tracer_manager.open_tracer(
                graph_id=pipeline_run_id,
                data_inclusion=execution_config.graph_config.data_inclusion,
                pipeline_ref_domain=pipe.domain_code,
                pipeline_ref_main_pipe=pipe_code,
                event_log=event_log,
                workflow_id="direct",
                pipeline_run_id=pipeline_run_id,
            )

        # TODO: rethink this, it's not forcing
        if pipe_run_mode is None:
            if run_mode_from_env := get_optional_env(key=FORCE_DRY_RUN_MODE_ENV_KEY):
                pipe_run_mode = PipeRunMode(run_mode_from_env)
            else:
                pipe_run_mode = PipeRunMode.LIVE

        get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)
        registry_opened = True

        # Set event log on the report delegate for distributed usage event emission
        if event_log is not None:
            get_report_delegate().set_event_log(
                context_key=pipeline_run_id,
                event_log=event_log,
                workflow_id="direct",
                pipeline_run_id=pipeline_run_id,
            )

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

        # Seam 2: build the pipe job (pure — no registration, telemetry, graph open, or library mutation).
        pipe_job = await prepare_pipe_job(
            pipe=pipe,
            library_id=library_id,
            execution_config=execution_config,
            pipe_run_mode=pipe_run_mode,
            pipeline_run_id=pipeline_run_id,
            user_id=user_id,
            inputs=inputs,
            search_domain_codes=search_domain_codes,
            graph_context=graph_context,
            otel_context=otel_context,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            request_id=request_id,
        )

        properties = {
            EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe.pipe_type,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_EXECUTE, properties=properties)

        success = True
        return pipe_job, pipeline_run_id, library_id
    finally:
        if not success:
            # Error-path-only cleanup for failures after the library was acquired: tear down the graph
            # tracer, event-log state, the report registry, and the library, and restore the outer
            # current-library, then let the exception propagate. Uses try/finally (not except) so a
            # BaseException — e.g. asyncio.CancelledError — is covered too. acquire_library owns teardown
            # for load-time failures (before this try); this block owns the post-acquire window.
            if graph_context is not None:
                tracer_manager = GraphTracerManager.get_instance()
                if tracer_manager is not None:
                    tracer_manager.close_tracer(pipeline_run_id)
            if event_log is not None:
                get_report_delegate().clear_event_log(context_key=pipeline_run_id)
            # Close the per-run registry only if open_registry actually ran: close_registry bare-pops
            # (KeyError on miss) and this finally also runs for failures *before* open_registry.
            if registry_opened:
                get_report_delegate().close_registry(pipeline_run_id=pipeline_run_id)
            # Restore the caller's outer current-library FIRST so the guarantee survives a teardown raise,
            # then tear the library down — mirroring validate_bundle. set_current_library cannot take None,
            # so route the "no outer was set" case through clear_current_library.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)
