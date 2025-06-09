from abc import abstractmethod
from typing import List, Optional

from typing_extensions import override

from pipelex import log
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol


class ImggWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        imgg_engine: ImggEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.imgg_engine = imgg_engine

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Img Worker using:\n{self.imgg_engine.desc}"

    def _check_can_perform_job(self, imgg_job: ImggJob):
        # This can be overridden by subclasses for specific checks
        pass

    async def gen_image(
        self,
        imgg_job: ImggJob,
    ) -> GeneratedImage:
        log.debug(f"Image gen worker gen_image:\n{self.imgg_engine.desc}")

        # Verify that the job is valid
        imgg_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(imgg_job=imgg_job)

        # metadata
        imgg_job.job_metadata.unit_job_id = UnitJobId.IMGG_TEXT_TO_IMAGE

        # Prepare job
        imgg_job.imgg_job_before_start(imgg_engine=self.imgg_engine)

        # Execute job
        result = await self._gen_image(imgg_job=imgg_job)

        # Report job
        imgg_job.imgg_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=imgg_job)

        return result

    @abstractmethod
    async def _gen_image(
        self,
        imgg_job: ImggJob,
    ) -> GeneratedImage:
        pass

    async def gen_image_list(
        self,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> List[GeneratedImage]:
        log.debug(f"Image gen worker gen_image_list:\n{self.imgg_engine.desc}")

        # Verify that the job is valid
        imgg_job.validate_before_execution()

        # Verify feasibility
        self._check_can_perform_job(imgg_job=imgg_job)

        # metadata
        imgg_job.job_metadata.unit_job_id = UnitJobId.IMGG_TEXT_TO_IMAGE

        # Prepare job
        imgg_job.imgg_job_before_start(imgg_engine=self.imgg_engine)

        # Execute job
        result = await self._gen_image_list(imgg_job=imgg_job, nb_images=nb_images)

        # Report job
        imgg_job.imgg_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=imgg_job)

        return result

    @abstractmethod
    async def _gen_image_list(
        self,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> List[GeneratedImage]:
        pass
