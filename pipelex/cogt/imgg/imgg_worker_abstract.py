from abc import abstractmethod
from functools import wraps
from typing import Any, Callable, List, Optional, TypeVar, cast

from typing_extensions import Awaitable, override

from pipelex import log
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.pipeline.job_metadata import UnitJobId

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def imgg_job_func(func: F) -> F:
    @wraps(func)
    async def wrapper(
        self: Any,
        imgg_job: ImggJob,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        log.debug(f"Working — {func.__name__} using:\n{self.imgg_engine.desc}")

        # Verify that the job is valid
        imgg_job.validate_before_execution()

        # Verify feasibility
        self.check_can_perform_job(imgg_job=imgg_job)
        # TODO: check can generate object (where it will be appropriate)

        # metadata
        imgg_job.job_metadata.unit_job_id = UnitJobId.IMGG_TEXT_TO_IMAGE

        # Prepare job
        imgg_job.imgg_job_before_start(imgg_engine=self.imgg_engine)

        # Execute job
        result = await func(self, imgg_job, *args, **kwargs)

        # Report job
        imgg_job.imgg_job_after_complete()
        if self.report_delegate:
            self.report_delegate.report_inference_job(inference_job=imgg_job)

        return result

    return cast(F, wrapper)


class ImggWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        imgg_engine: ImggEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        InferenceWorkerAbstract.__init__(self, report_delegate=report_delegate)
        self.imgg_engine = imgg_engine

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Img Worker using:\n{self.imgg_engine.desc}"

    def check_can_perform_job(self, imgg_job: ImggJob):
        pass

    @abstractmethod
    async def gen_image(
        self,
        imgg_job: ImggJob,
    ) -> GeneratedImage:
        pass

    @abstractmethod
    async def gen_image_list(
        self,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> List[GeneratedImage]:
        pass
