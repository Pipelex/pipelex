from typing import Any, List, Optional

from fal_client import AsyncClient, InProgress
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract, imgg_job_func
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.plugins.fal.fal_factory import FalFactory


class FalImggWorker(ImggWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        imgg_engine: ImggEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(imgg_engine=imgg_engine, report_delegate=report_delegate)

        if not isinstance(sdk_instance, AsyncClient):
            raise SdkTypeError(f"Provided Imgg sdk_instance is not of type fal_client.AsyncClient: it's a '{type(sdk_instance)}'")

        self.fal_async_client = sdk_instance

    @override
    @imgg_job_func
    async def gen_image(
        self,
        imgg_job: ImggJob,
    ) -> GeneratedImage:
        application = FalFactory.make_fal_application(imgg_engine=self.imgg_engine)
        arguments = FalFactory.make_fal_arguments(
            fal_application=application,
            imgg_job=imgg_job,
            nb_images=1,
        )
        log.verbose(arguments, title=f"Fal arguments, application={application}")
        handler = await self.fal_async_client.submit(
            application=application,
            arguments=arguments,
        )

        log_index = 0
        async for event in handler.iter_events(with_logs=True):
            if isinstance(event, InProgress):
                if not event.logs:
                    continue
                new_logs = event.logs[log_index:]
                for event_log in new_logs:
                    print(event_log["message"])
                log_index = len(event.logs)

        fal_result = await handler.get()
        generated_image = FalFactory.make_generated_image(fal_result=fal_result)
        log.verbose(generated_image, title="generated_image")
        return generated_image

    @override
    @imgg_job_func
    async def gen_image_list(
        self,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> List[GeneratedImage]:
        application = FalFactory.make_fal_application(imgg_engine=self.imgg_engine)
        arguments = FalFactory.make_fal_arguments(
            fal_application=application,
            imgg_job=imgg_job,
            nb_images=nb_images,
        )
        handler = await self.fal_async_client.submit(
            application=application,
            arguments=arguments,
        )

        log_index = 0
        async for event in handler.iter_events(with_logs=True):
            if isinstance(event, InProgress):
                if not event.logs:
                    continue
                new_fal_logs = event.logs[log_index:]
                for fal_log in new_fal_logs:
                    log.debug(fal_log["message"], title="FAL Log")
                log_index = len(event.logs)

        fal_result = await handler.get()
        generated_image_list = FalFactory.make_generated_image_list(fal_result=fal_result)
        log.verbose(generated_image_list, title="generated_image_list")
        return generated_image_list
