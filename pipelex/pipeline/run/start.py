import asyncio

from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_pipe_router
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import VariableMultiplicity
from pipelex.pipeline.run.setup import pipeline_run_setup


async def start_pipeline(
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
) -> tuple[str, asyncio.Task[PipeOutput]]:
    """Start a pipeline in the background.

    This function mirrors *execute_pipeline* but returns immediately with the
    ``pipeline_run_id`` and a task instead of waiting for the pipe run to complete.
    The actual execution is scheduled on the current event-loop using
    :pyfunc:`asyncio.create_task`.

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
    tuple[str, asyncio.Task[PipeOutput]]
        The ``pipeline_run_id`` of the newly started pipeline and a task that
        can be awaited to get the pipe output.

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

    task: asyncio.Task[PipeOutput] = asyncio.create_task(get_pipe_router().run(pipe_job))

    return pipeline_run_id, task
