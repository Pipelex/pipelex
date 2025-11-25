from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
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
from pipelex.pipeline.run.setup import pipeline_run_setup
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome


async def execute_pipeline(
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    plx_content: str | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domains: list[str] | None = None,
) -> PipeOutput:
    """Execute a pipeline and wait for its completion.

    This function executes a pipe and returns its output along with the pipeline run ID.
    Unlike *start_pipeline*, this function waits for the pipe execution to complete
    before returning, and it returns the output in addition to the pipeline run ID.

    Parameters
    ----------
    library_id:
        The library ID to use for the pipeline execution. If not provided, the library_id will be set to the pipeline run ID.
    library_dirs:
        List of library directories to load. If not provided, the current working directory will be used.
    pipe_code:
        The code identifying the pipeline to execute.
    plx_content:
        Content of the pipeline bundle to execute.
    inputs:
        Inputs passed to the pipeline.
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity.
    dynamic_output_concept_code:
        Override the dynamic output concept code.
    pipe_run_mode:
        Pipe run mode: if specified, it must be ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``.
        If not specified, the pipe run mode is inferred from the environment variable
        ``PIPELEX_FORCE_DRY_RUN_MODE``. If the environment variable is not set,
        the pipe run mode is ``PipeRunMode.LIVE``.
    search_domains:
        List of domains to search for pipes.

    Returns:
    -------
    PipeOutput
        The pipe output from the execution.

    """
    pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
        library_id=library_id,
        library_dirs=library_dirs,
        pipe_code=pipe_code,
        plx_content=plx_content,
        inputs=inputs,
        output_name=output_name,
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
        pipe_run_mode=pipe_run_mode,
        search_domains=search_domains,
    )

    try:
        pipe_output = await get_pipe_router().run(pipe_job)
    except PipeRouterError as exc:
        raise PipelineExecutionError(
            message=exc.message,
            run_mode=pipe_job.pipe_run_params.run_mode,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=pipe_job.pipe_run_params.pipe_stack,
        ) from exc
    finally:
        library = get_library_manager().get_library(library_id=library_id)
        library.teardown()
        teardown_current_library()
    properties = {
        EventProperty.PIPELINE_RUN_ID: pipeline_run_id,
        EventProperty.PIPE_TYPE: pipe_job.pipe.pipe_type,
        EventProperty.PIPELINE_EXECUTE_OUTCOME: Outcome.SUCCESS,
    }
    get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
    return pipe_output
