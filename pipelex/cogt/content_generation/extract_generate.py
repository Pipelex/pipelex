from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.core.stuffs.page_content import PageContent
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


async def extract_gen_pages_and_store(
    extract_assignment: ExtractAssignment,
    generated_content_factory: GeneratedContentFactory,
) -> list[PageContent]:
    """Extract pages and store extracted images, returning PageContent with URLs (no raw binary data)."""
    extract_output = await extract_gen_pages(extract_assignment)
    return await generated_content_factory.make_page_contents(
        primary_id=extract_assignment.job_metadata.user_id,
        secondary_id=extract_assignment.job_metadata.pipeline_run_id,
        extract_output=extract_output,
    )
