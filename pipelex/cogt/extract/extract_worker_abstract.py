from abc import abstractmethod
from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol


class ExtractWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.extra_config = extra_config
        self.inference_model = inference_model

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"OCR-Worker:{self.inference_model.tag}"

    def _check_can_perform_job(self, extract_job: ExtractJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        log.debug(f"Extract Worker extract_pages:\n{self.inference_model.desc}")

        # Verify that the job is valid
        extract_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(extract_job=extract_job)
        # TODO: check can generate object (where it will be appropriate)

        # metadata
        extract_job.job_metadata.unit_job_id = UnitJobId.EXTRACT_PAGES

        # Prepare job
        extract_job.extract_job_before_start()

        # Execute job
        result = await self._extract_pages(extract_job=extract_job)

        # Report job
        extract_job.extract_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=extract_job)

        return result

    @abstractmethod
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        pass
