from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.ocr.ocr_job_factory import ExtractJobFactory
from pipelex.cogt.ocr.ocr_output import ExtractOutput
from pipelex.hub import get_ocr_worker


async def extract_gen_pages(ocr_assignment: ExtractAssignment) -> ExtractOutput:
    ocr_worker = get_ocr_worker(ocr_handle=ocr_assignment.extract_handle)
    ocr_job = ExtractJobFactory.make_ocr_job(
        extract_input=ocr_assignment.extract_input,
        extract_job_params=ocr_assignment.extract_job_params,
        extract_job_config=ocr_assignment.extract_job_config,
        job_metadata=ocr_assignment.job_metadata,
    )
    return await ocr_worker.extract_pages(extract_job=ocr_job)
