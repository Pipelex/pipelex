from abc import abstractmethod
from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError
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
        return f"Extraction using {self.inference_model.desc}"

    @property
    def is_pdf_supported(self) -> bool:
        return self.inference_model.is_pdf_supported_for_extract

    @property
    def is_image_supported(self) -> bool:
        return self.inference_model.is_image_supported_for_extract

    @property
    def is_caption_supported(self) -> bool:
        return self.inference_model.is_caption_supported_for_extract

    def _check_can_perform_job(self, extract_job: ExtractJob):
        # This can be overridden by subclasses for specific checks
        extract_input = extract_job.extract_input
        if extract_input.image_uri:
            if not self.inference_model.is_image_supported_for_extract:
                msg = f"Extract engine '{self.inference_model.tag}' does not support image extraction."
                raise ExtractCapabilityError(msg)
        elif extract_input.document_uri:
            if not self.inference_model.is_pdf_supported_for_extract:
                msg = f"Extract engine '{self.inference_model.tag}' does not support PDF extraction."
                raise ExtractCapabilityError(msg)
        if extract_job.job_params.should_caption_images:
            if not self.inference_model.is_caption_supported_for_extract:
                msg = f"Extract engine '{self.inference_model.tag}' does not support image captioning."
                raise ExtractCapabilityError(msg)

    async def extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        log.dev(f"✨ {self.desc} ✨")

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
