from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import OcrAssignment
from pipelex.cogt.content_generation.ocr_generate import ocr_gen_extract_pages
from pipelex.cogt.ocr.ocr_output import OcrOutput


@activity.defn
async def act_ocr_gen_extract_pages(ocr_assignment: OcrAssignment) -> OcrOutput:
    log.dev("act_ocr_gen_extract_pages")
    return await ocr_gen_extract_pages(ocr_assignment=ocr_assignment)
