from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams, OcrJobReport
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class OcrJobFactory:
    @classmethod
    def make_ocr_job(
        cls,
        ocr_input: OcrInput,
        ocr_job_params: OcrJobParams | None = None,
        ocr_job_config: OcrJobConfig | None = None,
        job_metadata: JobMetadata | None = None,
    ) -> OcrJob:
        # TODO: manage the param default through the config
        # ocr_config = get_config().cogt.ocr_config
        job_metadata = job_metadata or JobMetadata(
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
