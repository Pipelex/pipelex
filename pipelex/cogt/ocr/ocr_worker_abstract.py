from abc import abstractmethod
from typing import Optional

from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol


class OcrWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        ocr_engine: OcrEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.ocr_engine = ocr_engine

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Ocr Worker using:\n{self.ocr_engine.desc}"

    def _check_can_perform_job(self, ocr_job: OcrJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def ocr_extract_pages(
        self,
        ocr_job: OcrJob,
    ) -> OcrOutput:
        log.debug(f"OCR Worker ocr_extract_pages:\n{self.ocr_engine.desc}")

        # Verify that the job is valid
        ocr_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(ocr_job=ocr_job)
        # TODO: check can generate object (where it will be appropriate)

        # metadata
        ocr_job.job_metadata.unit_job_id = UnitJobId.OCR_EXTRACT_PAGES

        # Prepare job
        ocr_job.ocr_job_before_start(ocr_engine=self.ocr_engine)

        # Execute job
        result = await self._ocr_extract_pages(ocr_job=ocr_job)

        # Report job
        ocr_job.ocr_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=ocr_job)

        return result

    @abstractmethod
    async def _ocr_extract_pages(
        self,
        ocr_job: OcrJob,
    ) -> OcrOutput:
        pass
