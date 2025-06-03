from typing import Optional, Tuple

from pipelex import pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.hub import get_pipe_router, get_pipeline_manager, get_report_delegate, get_required_pipe
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipeline.job_metadata import JobMetadata


async def execute_pipeline(
    pipe_code: str,
    working_memory: Optional[WorkingMemory] = None,
    output_name: Optional[str] = None,
    output_multiplicity: Optional[PipeOutputMultiplicity] = None,
    dynamic_output_concept_code: Optional[str] = None,
) -> Tuple[PipeOutput, str]:
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
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity.
    dynamic_output_concept_code:
        Override the dynamic output concept code.

    Returns
    -------
    Tuple[PipeOutput, str]
        A tuple containing the pipe output and the pipeline run ID.
    """
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
    )

    pretty_print(pipe, title=f"Running pipe '{pipe_code}'")
    if working_memory:
        working_memory.pretty_print_summary()

    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=output_name,
    )

    return await get_pipe_router().run_pipe_job(pipe_job), pipeline_run_id
