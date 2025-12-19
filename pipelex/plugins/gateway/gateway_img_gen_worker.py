from __future__ import annotations

from typing import TYPE_CHECKING, Any

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.plugins.fal.fal_poller import FalPoller
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.tools.misc.base_64_utils import prefixed_base64_str_from_base64_str

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol


class GatewayImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided ImgGen sdk_instance for {self.__class__.__name__} is not of type portkey_ai.AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImage:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
        )

        endpoint_path = f"/{self.inference_model.model_id}"
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        try:
            # TODO: add portkey tracing headers when enabled
            response = await self.portkey_client.with_options(config=config_id).post(url=endpoint_path, **args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            msg = f"Image generation service error for model '{self.inference_model.model_id}': {error_summary}"
            raise ImgGenGenerationError(msg) from exc

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.model_id}' via Portkey"
            raise ImgGenGenerationError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        response_dict: dict[str, Any] = response.model_dump()
        generated_images: list[GeneratedImage] = []

        if images := response_dict.get("data"):
            size = response_dict.get("size")
            if not isinstance(size, str):
                msg = f"Size from img gen response is not a string: '{size}'"
                raise ImgGenGenerationError(msg)
            size_split = size.split("x")
            if len(size_split) != 2:
                msg = f"Size from img gen response is not a valid size: '{size}'"
                raise ImgGenGenerationError(msg)
            width_str, height_str = size_split
            width = int(width_str)
            height = int(height_str)
            for image in images:
                b64_str = image.get("b64_json")
                if not isinstance(b64_str, str):
                    msg = f"No base64 image data received from model '{self.inference_model.model_id}'"
                    raise ImgGenGenerationError(msg)
                base64_url = prefixed_base64_str_from_base64_str(b64_str=b64_str)
                generated_images.append(
                    GeneratedImage(
                        url=base64_url,
                        width=width,
                        height=height,
                    ),
                )

        elif response_dict.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            # Handle FAL queue responses that require polling
            fal_poller = FalPoller()
            response_dict = await fal_poller.poll_queue_until_complete(response_dict=response_dict)

            for item in response_dict.get("images", []):
                generated_image = GeneratedImage(url=item.get("url"), width=item.get("width"), height=item.get("height"))
                generated_images.append(generated_image)
        else:
            msg = f"Unexpected response from model '{self.inference_model.model_id}' has no 'data' or 'images' key"
            raise ImgGenGenerationError(msg)

        return generated_images
