from abc import abstractmethod
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from typing_extensions import Awaitable, override

from pipelex import log
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.pipeline.job_metadata import UnitJobId

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def ocr_job_func(func: F) -> F:
    @wraps(func)
    async def wrapper(
        self: Any,
        ocr_job: OcrJob,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        log.debug(f"Working — {func.__name__} using:\n{self.ocr_engine.desc}")

        # Verify that the job is valid
        ocr_job.validate_before_execution()

        # Verify feasibility
        self.check_can_perform_job(ocr_job=ocr_job)
        # TODO: check can generate object (where it will be appropriate)

        # metadata
        ocr_job.job_metadata.unit_job_id = UnitJobId.OCR_EXTRACT_PAGES

        # Prepare job
        ocr_job.ocr_job_before_start(ocr_engine=self.ocr_engine)

        # Execute job
        result = await func(self, ocr_job, *args, **kwargs)

        # Report job
        ocr_job.ocr_job_after_complete()
        if self.report_delegate:
            self.report_delegate.report_inference_job(inference_job=ocr_job)

        return result

    return cast(F, wrapper)


class OcrWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        ocr_engine: OcrEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        InferenceWorkerAbstract.__init__(self, report_delegate=report_delegate)
        self.ocr_engine = ocr_engine

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Ocr Worker using:\n{self.ocr_engine.desc}"

    def check_can_perform_job(self, ocr_job: OcrJob):
        pass

    @abstractmethod
    async def ocr_extract_pages(
        self,
        ocr_job: OcrJob,
    ) -> OcrOutput:
        pass
