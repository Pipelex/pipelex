from pipelex.cogt.content_generation.assignment_models import OcrAssignment
from pipelex.cogt.ocr.ocr_job_factory import OcrJobFactory
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.hub import get_ocr_worker


async def ocr_gen_extract_pages(ocr_assignment: OcrAssignment) -> OcrOutput:
    ocr_worker = get_ocr_worker(ocr_handle=ocr_assignment.ocr_handle)
    ocr_job = OcrJobFactory.make_ocr_job(
        ocr_input=ocr_assignment.ocr_input,
        ocr_job_params=ocr_assignment.ocr_job_params,
        ocr_job_config=ocr_assignment.ocr_job_config,
        job_metadata=ocr_assignment.job_metadata,
    )
    return await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
