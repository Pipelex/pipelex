from typing import Any

from fal_client import AsyncClient
from fal_client.auth import MissingCredentialsError
from fal_client.client import FalClientError, FalClientHTTPError, FalClientTimeoutError
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import extract_fal_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.providers.fal.fal_factory import FalFactory
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
        *,
        nb_images: int,
    ) -> Any:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg, error_category=InferenceErrorCategory.CONFIGURATION)
        args_dict = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
            model_name=self.inference_model.name,
        )
        fal_application = args_dict.pop("model", None)
        if fal_application is None:
            msg = f"Model '{self.inference_model.name}' rules must include a 'model_choice' entry"
            raise ImgGenParameterError(msg, error_category=InferenceErrorCategory.CONFIGURATION)
        try:
            handler = await self.fal_async_client.submit(
                application=fal_application,
                arguments=args_dict,
            )
            return await handler.get()
        except (MissingCredentialsError, FalClientHTTPError, FalClientTimeoutError, FalClientError) as exc:
            metadata = extract_fal_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.IMG_GEN,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from exc

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=1)
        return FalFactory.make_generated_image(fal_result=fal_result)

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=nb_images)
        return FalFactory.make_generated_image_list(fal_result=fal_result)
