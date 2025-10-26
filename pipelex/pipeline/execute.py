from typing import TYPE_CHECKING

from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import PipeExecutionError, PipelineExecutionError, PipeRouterError
from pipelex.hub import (
    get_library_manager,
    get_pipe_router,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
    get_telemetry_manager,
)
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import (
    FORCE_DRY_RUN_MODE_ENV_KEY,
    VariableMultiplicity,
)
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.validate_plx import validate_plx
from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


async def execute_pipeline(
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
    Tuple[PipeOutput, str]
        A tuple containing the pipe output and the pipeline run ID.

    """
    if not plx_content and not pipe_code:
        msg = "Either pipe_code or plx_content must be provided to the API execute_pipeline."
        raise ValueError(msg)

    pipe: PipeAbstract | None = None
    blueprint: PipelexBundleBlueprint | None = None

    if plx_content:
        blueprint, _ = await validate_plx(plx_content=plx_content, remove_after_validation=False)

        if pipe_code:
            pipe = get_required_pipe(pipe_code=pipe_code)
        elif blueprint.main_pipe:
            pipe = get_required_pipe(pipe_code=blueprint.main_pipe)
        else:
            msg = "No pipe code or main pipe in the PLX content provided to the API execute_pipeline."
            raise PipeExecutionError(message=msg)
    elif pipe_code:
        pipe = get_required_pipe(pipe_code=pipe_code)
    else:
        msg = "Either provide pipe_code or plx_content to the API execute_pipeline. 'pipe_code' must be provided when 'plx_content' is None"
        raise PipeExecutionError(message=msg)

    search_domains = search_domains or []
    if pipe.domain not in search_domains:
        search_domains.insert(0, pipe.domain)

    working_memory: WorkingMemory | None = None

    if inputs:
        if isinstance(inputs, WorkingMemory):
            working_memory = inputs
        else:
            working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                pipeline_inputs=inputs,
                search_domains=search_domains,
            )

    if pipe_run_mode is None:
        if run_mode_from_env := get_optional_env(key=FORCE_DRY_RUN_MODE_ENV_KEY):
            pipe_run_mode = PipeRunMode(run_mode_from_env)
        else:
            pipe_run_mode = PipeRunMode.LIVE

    pipeline = get_pipeline_manager().add_new_pipeline()
    get_report_delegate().open_registry(pipeline_run_id=pipeline.pipeline_run_id)

    job_metadata = JobMetadata(
        pipeline_run_id=pipeline.pipeline_run_id,
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
        if plx_content and blueprint is not None:
            get_library_manager().remove_from_blueprint(blueprint=blueprint)
    properties = {
        EventProperty.PIPELINE_RUN_ID: job_metadata.pipeline_run_id,
        EventProperty.PIPE_TYPE: pipe.pipe_type,
        EventProperty.PIPELINE_EXECUTE_OUTCOME: Outcome.SUCCESS,
    }
    get_telemetry_manager().track_event(event_name=EventName.PIPELINE_COMPLETE, properties=properties)
    return pipe_output
