from typing import Any

from fal_client import AsyncClient, InProgress
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.fal.fal_factory import FalFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol


class FalImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncClient):
            msg = f"Provided ImgGen sdk_instance is not of type fal_client.AsyncClient: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.fal_async_client = sdk_instance

    async def _submit_and_get_result(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> Any:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
        )
        fal_application = self.inference_model.model_id
        log.verbose(args_dict, title=f"Fal arguments, application={fal_application}")
        handler = await self.fal_async_client.submit(
            application=fal_application,
            arguments=args_dict,
        )

        log_index = 0
        async for event in handler.iter_events(with_logs=True):
            if isinstance(event, InProgress):
                if not event.logs:
                    continue
                new_logs = event.logs[log_index:]
                for event_log in new_logs:
                    log.verbose(event_log["message"], title="FAL Log")
                log_index = len(event.logs)

        return await handler.get()

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=1)
        generated_image = FalFactory.make_generated_image(fal_result=fal_result)
        log.verbose(generated_image, title="generated_image")
        return generated_image

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=nb_images)
        generated_image_list = FalFactory.make_generated_image_list(fal_result=fal_result)
        log.verbose(generated_image_list, title="generated_image_list")
        return generated_image_list
