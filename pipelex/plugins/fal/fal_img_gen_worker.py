from typing import Any

from fal_client import AsyncClient, InProgress
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.fal.fal_factory import FalFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.terminal_utils import print_to_stderr


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

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImage:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        common_args = FalFactory.make_common_args(img_gen_job=img_gen_job, nb_images=1)
        args_for_model = ImgGenArgsFactory.make_args_for_model(model_rules=self.inference_model.rules, job_params=img_gen_job.job_params)
        args_dict: dict[str, Any] = {**common_args, **args_for_model}
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
                    print_to_stderr(event_log["message"])
                log_index = len(event.logs)

        fal_result = await handler.get()
        generated_image = FalFactory.make_generated_image(fal_result=fal_result)
        log.verbose(generated_image, title="generated_image")
        return generated_image

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        common_args = FalFactory.make_common_args(img_gen_job=img_gen_job, nb_images=nb_images)
        args_for_model = ImgGenArgsFactory.make_args_for_model(model_rules=self.inference_model.rules, job_params=img_gen_job.job_params)
        args_dict: dict[str, Any] = {**common_args, **args_for_model}
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
                new_fal_logs = event.logs[log_index:]
                for fal_log in new_fal_logs:
                    log.verbose(fal_log["message"], title="FAL Log")
                log_index = len(event.logs)

        fal_result = await handler.get()
        generated_image_list = FalFactory.make_generated_image_list(fal_result=fal_result)
        log.verbose(generated_image_list, title="generated_image_list")
        return generated_image_list
