import asyncio

from pipelex.client.protocol import CompactMemory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import StartPipelineError
from pipelex.hub import get_pipe_router, get_pipeline_manager, get_report_delegate, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeOutputMultiplicity, PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


async def start_pipeline(
    pipe_code: str,
    working_memory: WorkingMemory | None = None,
    input_memory: CompactMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: PipeOutputMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
) -> asyncio.Task[PipeOutput]:
    """Start a pipeline in the background.

    This function mirrors *execute_pipeline* but returns immediately with the
    ``pipeline_run_id`` instead of waiting for the pipe run to complete. The
    actual execution is scheduled on the current event-loop using
    :pyfunc:`asyncio.create_task`.

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
        Pipe run mode: ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``.

    Returns:
    -------
    Tuple[str, asyncio.Task[PipeOutput]]
        The ``pipeline_run_id`` of the newly started pipeline and a task that
        can be awaited to get the pipe output.

    """
    if working_memory and input_memory:
        msg = f"Cannot pass both working_memory and input_memory to `start_pipeline` {pipe_code=}"
        raise StartPipelineError(msg)

    if input_memory:
        working_memory = WorkingMemoryFactory.make_from_compact_memory(input_memory)

    pipeline = get_pipeline_manager().add_new_pipeline()
    pipeline_run_id = pipeline.pipeline_run_id
    get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)
    pipe = get_required_pipe(pipe_code=pipe_code)

    job_metadata = JobMetadata(
        pipeline_run_id=pipeline_run_id,
    )

    pipe_run_params = PipeRunParamsFactory.make_run_params(
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
        pipe_run_mode=pipe_run_mode,
    )

    if working_memory:
        working_memory.pretty_print_summary()

    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=output_name,
    )

    # Launch execution without awaiting the result.
    task: asyncio.Task[PipeOutput] = asyncio.create_task(get_pipe_router().run(pipe_job))

    return task
