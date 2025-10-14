from pipelex.client.protocol import ImplicitMemory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import PipelineInputError
from pipelex.hub import (
    get_pipe_router,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
)
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import (
    FORCE_DRY_RUN_MODE_ENV_KEY,
    PipeOutputMultiplicity,
    PipeRunMode,
)
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.environment import get_optional_env


async def execute_pipeline(
    pipe_code: str,
    working_memory: WorkingMemory | None = None,
    input_memory: ImplicitMemory | None = None,
    search_domains: list[str] | None = None,
    output_name: str | None = None,
    output_multiplicity: PipeOutputMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
) -> PipeOutput:
    """Execute a pipeline and wait for its completion.

    This function executes a pipe and returns its output along with the pipeline run ID.
    Unlike *start_pipeline*, this function waits for the pipe execution to complete
    before returning, and it returns the output in addition to the pipeline run ID.

    Parameters
    ----------
    pipe_code:
        The code of the pipe to execute.
    working_memory:
        Optional ``WorkingMemory`` instance passed to the pipe.
    input_memory:
        Optional compact memory to pass to the pipe.
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
    search_domains = search_domains or []
    pipe = get_required_pipe(pipe_code=pipe_code)
    if pipe.domain not in search_domains:
        search_domains.insert(0, pipe.domain)

    # Can be either working_memory or compact_memory or neither, but not both
    if working_memory and input_memory:
        msg = f"Cannot pass both working_memory and input_memory to `execute_pipeline` {pipe_code=}"
        raise PipelineInputError(msg)
    if input_memory:
        working_memory = WorkingMemoryFactory.make_from_implicit_memory(
            implicit_memory=input_memory,
            search_domains=search_domains,
        )

    if pipe_run_mode is None:
        if run_mode_from_env := get_optional_env(key=FORCE_DRY_RUN_MODE_ENV_KEY):
            pipe_run_mode = PipeRunMode(run_mode_from_env)
        else:
            pipe_run_mode = PipeRunMode.LIVE

    pipeline = get_pipeline_manager().add_new_pipeline()
    pipeline_run_id = pipeline.pipeline_run_id
    get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)

    job_metadata = JobMetadata(
        pipeline_run_id=pipeline_run_id,
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

    return await get_pipe_router().run(pipe_job)
