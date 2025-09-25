from abc import abstractmethod

from typing_extensions import override

from pipelex import log
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol


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

    def _check_can_perform_job(self, img_gen_job: ImgGenJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImage:
        log.debug(f"Image gen worker gen_image using {self.desc}")

        # Verify that the job is valid
        img_gen_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(img_gen_job=img_gen_job)

        # metadata
        img_gen_job.job_metadata.unit_job_id = UnitJobId.IMG_GEN_TEXT_TO_IMAGE

        # Prepare job
        img_gen_job.img_gen_job_before_start()

        # Execute job
        result = await self._gen_image(img_gen_job=img_gen_job)

        # Report job
        img_gen_job.img_gen_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=img_gen_job)

        return result

    @abstractmethod
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImage:
        pass

    async def gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        log.debug(f"Image gen worker gen_image_list using {self.desc}")

        # Verify that the job is valid
        img_gen_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(img_gen_job=img_gen_job)

        # metadata
        img_gen_job.job_metadata.unit_job_id = UnitJobId.IMG_GEN_TEXT_TO_IMAGE

        # Prepare job
        img_gen_job.img_gen_job_before_start()

        # Execute job
        result = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=nb_images)

        # Report job
        img_gen_job.img_gen_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=img_gen_job)

        return result

    @abstractmethod
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        pass
