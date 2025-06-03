from typing import Optional

from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams, OcrJobReport
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class OcrJobFactory:
    @classmethod
    def make_ocr_job(
        cls,
        ocr_input: OcrInput,
        ocr_job_params: Optional[OcrJobParams] = None,
        ocr_job_config: Optional[OcrJobConfig] = None,
        job_metadata: Optional[JobMetadata] = None,
    ) -> OcrJob:
        config = get_config()
        # TODO: manahge the param default sthrough the config
        # ocr_config = get_config().cogt.ocr_config
        job_metadata = job_metadata or JobMetadata(
            top_job_id=f"OCRJob for {config.project_name}",
            job_category=JobCategory.OCR_JOB,
        )
        job_params = ocr_job_params or OcrJobParams.make_default_ocr_job_params()
        job_config = ocr_job_config or OcrJobConfig()
        job_report = OcrJobReport()

        return OcrJob(
            job_metadata=job_metadata,
            ocr_input=ocr_input,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )
