from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.hub import get_extract_worker


async def extract_gen_pages(extract_assignment: ExtractAssignment) -> ExtractOutput:
    extract_worker = get_extract_worker(extract_handle=extract_assignment.extract_handle)
    extract_job = ExtractJobFactory.make_extract_job(
        extract_input=extract_assignment.extract_input,
        extract_job_params=extract_assignment.extract_job_params,
        extract_job_config=extract_assignment.extract_job_config,
        job_metadata=extract_assignment.job_metadata,
    )
    return await extract_worker.extract_pages(extract_job=extract_job)
