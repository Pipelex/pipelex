from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages
from pipelex.cogt.extract.extract_output import ExtractOutput


@activity.defn
async def act_extract_gen_extract_pages(extract_assignment: ExtractAssignment) -> ExtractOutput:
    log.dev("act_extract_gen_extract_pages")
    return await extract_gen_pages(extract_assignment=extract_assignment)
