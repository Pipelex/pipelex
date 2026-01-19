from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipelex.base_exceptions import PipelexError
from pipelex.client.protocol import PipelineInputs
from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import (
    get_library_manager,
    get_pipe_router,
    get_telemetry_manager,
    teardown_current_library,
)
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import VariableMultiplicity
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome

if TYPE_CHECKING:
    from pipelex.pipe_run.pipe_job import PipeJob


async def execute_pipeline(
    user_id: str | None = None,
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
    execution_config: PipelineExecutionConfig | None = None,
) -> PipeOutput:
    """Execute a pipeline and wait for its completion.

    This function executes a pipe and returns its output. Unlike ``start_pipeline``,
    this function waits for the pipe execution to complete before returning.

    Parameters
    ----------
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
        ``main_pipe`` defined in the plx_content).
    plx_content:
        Complete PLX file content as a string. The pipe to execute is determined by
        ``pipe_code`` (if provided) or the ``main_pipe`` property in the PLX content.
        Can be combined with ``library_dirs`` to load additional definitions.
    bundle_uri:
        URI identifying the bundle. If ``plx_content`` is not provided and ``bundle_uri``
        points to a local file path, the content will be read from that file. Also used
        to detect if the bundle was already loaded from library directories (e.g., via
        PIPELEXPATH) to avoid duplicate domain registration.
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
        Unique identifier for the user.
    execution_config:
        Pipeline execution configuration including graph tracing settings.
        If provided, uses this config directly. If None, uses the default from
        ``get_config().pipelex.pipeline_execution_config``. Use the ``mock_inputs``
        field to generate mock data for missing required inputs during dry-run.

    Returns:
    -------
    PipeOutput
        The pipe output from the execution. If ``generate_graph`` was True, the
        execution graph is available in ``pipe_output.graph_spec``.

    """
    # Use provided config or get default
    execution_config = execution_config or get_config().pipelex.pipeline_execution_config

    # If plx_content is not provided but bundle_uri points to a file, read it
    if plx_content is None and bundle_uri is not None:
        bundle_path = Path(bundle_uri)
        if bundle_path.is_file():
            plx_content = bundle_path.read_text(encoding="utf-8")

    properties: dict[EventProperty, Any]
    graph_spec_result = None
    # These variables are set in pipeline_run_setup and needed in finally/except blocks
    pipeline_run_id: str | None = None
    library_id_resolved: str | None = None
    pipe_job: PipeJob | None = None
    try:
        pipe_job, pipeline_run_id, library_id_resolved = await pipeline_run_setup(
            execution_config=execution_config,
            library_id=library_id,
            library_dirs=library_dirs,
            pipe_code=pipe_code,
            plx_content=plx_content,
            bundle_uri=bundle_uri,
            inputs=inputs,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
            pipe_run_mode=pipe_run_mode,
            search_domain_codes=search_domain_codes,
            user_id=user_id,
        )
        pipe_output = await get_pipe_router().run(pipe_job)
    except PipeRouterError as exc:
        # PipeRouterError can only be raised by get_pipe_router().run(), so pipe_job is guaranteed to exist
        assert pipe_job is not None  # for type checker
        properties = {
            EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
            EventProperty.PIPELINE_OUTCOME: Outcome.FAILURE,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
        raise PipelineExecutionError(
            message=exc.message,
            run_mode=pipe_job.pipe_run_params.run_mode,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=pipe_job.pipe_run_params.pipe_stack,
        ) from exc
    except PipelexError as exc:
        # Catch other Pipelex errors that bypass the router's PipeRunError handling
        # (e.g., PipeRunInputsError raised directly from pipe_abstract.py)
        # If pipe_job is None, the error occurred during pipeline_run_setup before pipe_job was created
        if pipe_job is None:
            raise
        properties = {
            EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
            EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
            EventProperty.PIPELINE_OUTCOME: Outcome.FAILURE,
        }
        get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
        raise PipelineExecutionError(
            message=exc.message,
            run_mode=pipe_job.pipe_run_params.run_mode,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=pipe_job.pipe_run_params.pipe_stack,
        ) from exc
    finally:
        # Close graph tracer if it was opened (capture graph even on failure)
        # pipeline_run_id may be None if pipeline_run_setup failed early
        if execution_config.is_generate_graph and pipeline_run_id is not None:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                graph_spec_result = tracer_manager.close_tracer(pipeline_run_id)

        # Only teardown library if it was successfully created
        if library_id_resolved is not None:
            library = get_library_manager().get_library(library_id=library_id_resolved)
            library.teardown()
            teardown_current_library()

    # Assign graph spec to output (only reached on success, when pipe_output is bound)
    if graph_spec_result is not None:
        pipe_output.graph_spec = graph_spec_result

    properties = {
        EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
        EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
        EventProperty.PIPELINE_OUTCOME: Outcome.SUCCESS,
    }
    get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
    return pipe_output
