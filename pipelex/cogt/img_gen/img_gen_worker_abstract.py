from abc import abstractmethod

from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, ImgGenParameterError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_call_summary import InferenceCallSummary, InferenceOperation
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import UnitJobId


class ImgGenWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"ImgGen-Worker:{self.inference_model.tag}"

    @property
    def is_img2img_supported(self) -> bool:
        """Check if this worker supports image-to-image generation (input images)."""
        return self.inference_model.is_img2img_supported

    def _check_can_perform_job(self, img_gen_job: ImgGenJob):
        """Reject jobs the model cannot honor, before any provider call.

        Subclasses may override for provider-specific checks; overrides must call
        `super()._check_can_perform_job(img_gen_job=img_gen_job)` to keep the
        capability checks below.
        """
        if img_gen_job.img_gen_prompt.input_images and not self.inference_model.is_img2img_supported:
            msg = (
                f"Model '{self.inference_model.name}' does not accept image inputs, but input images were provided. "
                "Use an image model that supports image-to-image generation, or remove the input images."
            )
            raise ImgGenParameterError(msg)

    def _call_summary(self, *, img_gen_job: ImgGenJob) -> InferenceCallSummary:
        """The event the call ends with, its model and its usage read off the worker and the job it reports when it ends."""
        return InferenceCallSummary(
            operation=InferenceOperation.IMG_GEN,
            model_handle=self.inference_model.name,
            read_inference_model=lambda: self.inference_model,
            read_tokens_usage=lambda: img_gen_job.job_report.img_gen_tokens_usage,
        )

    async def gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        # The call ends with its summary event whichever way it ends, a refusal by the checks below included
        with self._call_summary(img_gen_job=img_gen_job):
            # Verify that the job is valid
            img_gen_job.validate_before_execution()

            # Verify feasibility
            self._check_can_perform_job(img_gen_job=img_gen_job)

            # metadata
            img_gen_job.job_metadata.unit_job_id = UnitJobId.IMG_GEN_TEXT_TO_IMAGE

            # Prepare job
            img_gen_job.img_gen_job_before_start(inference_model=self.inference_model)

            # Execute job
            try:
                result = await self._gen_image(img_gen_job=img_gen_job)
            except CogtError as exc:
                exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
                raise

            # Report job
            img_gen_job.img_gen_job_after_complete()
            if self.reporting_delegate:
                self.reporting_delegate.report_inference_job(inference_job=img_gen_job)

        return result

    @abstractmethod
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        pass

    async def gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        # The call ends with its summary event whichever way it ends, a refusal by the checks below included
        with self._call_summary(img_gen_job=img_gen_job):
            # Verify that the job is valid
            img_gen_job.validate_before_execution()

            # Verify feasibility
            self._check_can_perform_job(img_gen_job=img_gen_job)

            # metadata
            img_gen_job.job_metadata.unit_job_id = UnitJobId.IMG_GEN_TEXT_TO_IMAGE

            # Prepare job
            img_gen_job.img_gen_job_before_start(inference_model=self.inference_model)

            # Execute job
            try:
                result = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=nb_images)
            except CogtError as exc:
                exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
                raise

            # Report job
            img_gen_job.img_gen_job_after_complete()
            if self.reporting_delegate:
                self.reporting_delegate.report_inference_job(inference_job=img_gen_job)

        return result

    @abstractmethod
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        pass
