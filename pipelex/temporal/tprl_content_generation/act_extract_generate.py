from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages_and_store
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.core.stuffs.page_content import PageContent
from pipelex.hub import get_storage_provider


@activity.defn
async def act_extract_gen_extract_pages(extract_assignment: ExtractAssignment) -> list[PageContent]:
    """Extract pages and store extracted images, returning lightweight PageContent references.

    Large binary data (extracted images) is stored within the activity and never crosses
    the Temporal workflow boundary — only URLs are returned.
    """
    log.dev("act_extract_gen_extract_pages")
    storage_provider = get_storage_provider()
    generated_content_factory = GeneratedContentFactory(storage_provider=storage_provider)
    return await extract_gen_pages_and_store(
        extract_assignment=extract_assignment,
        generated_content_factory=generated_content_factory,
    )
