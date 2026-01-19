from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, Any

from PIL import Image
from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.plugins.fal.fal_poller import FalPoller
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_schemas import GatewayImgGenAzureFlux2Pro, GatewayImgGenAzureGptImage
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

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
    ) -> GeneratedImageRawDetails:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
        )

        endpoint_path = (self.inference_model.extra_headers or {}).get("endpoint_path") or f"/{self.inference_model.model_id}"
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        try:
            # TODO: add portkey tracing headers when enabled
            response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                url=endpoint_path,
                **args_dict,
            )
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

        # Giv en that different backends and different models can be used with this worker, we must interpret the response,
        # so we do it according to the shape we detext
        response_dict: dict[str, Any] = response.model_dump(serialize_as_any=True)
        generated_images: list[GeneratedImageRawDetails] = []
        if images := response_dict.get("data"):
            # Azure-shaped responses, model is either OpenAI's GPT Image or Black Forest Labs' Flux 2 Pro
            azure_gpt_image: GatewayImgGenAzureGptImage | None = None
            flux_2_pro_image: GatewayImgGenAzureFlux2Pro | None = None
            parsing_errors: str = ""
            try:
                response_azure_gpt_image = GatewayImgGenAzureGptImage.model_validate(response_dict)
                azure_gpt_image = response_azure_gpt_image
            except ValidationError as azure_gpt_image_error:
                validation_error_summary = format_pydantic_validation_error(azure_gpt_image_error)
                parsing_errors += f"Azure GPT Image: {validation_error_summary}\n"
                try:
                    response_flux_2_pro_image = GatewayImgGenAzureFlux2Pro.model_validate(response_dict)
                    flux_2_pro_image = response_flux_2_pro_image
                except ValidationError as flux_2_pro_image_error:
                    validation_error_summary = format_pydantic_validation_error(flux_2_pro_image_error)
                    parsing_errors += f"\n\nFlux 2 Pro: {validation_error_summary}\n"

            width: int
            height: int
            image_format: str | None
            if azure_gpt_image:
                image_format = response_dict.get("output_format")
                if not image_format:
                    msg = "No output format received from Gateway"
                    raise ImgGenGenerationError(msg)
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
            elif flux_2_pro_image:
                # Detect size and format from the first image's data
                first_image = images[0] if images else None
                if not first_image:
                    msg = "No images in Flux 2 Pro response"
                    raise ImgGenGenerationError(msg)
                first_base64 = first_image.get("b64_json")
                if not isinstance(first_base64, str):
                    msg = f"No base64 image data in first image from model '{self.inference_model.model_id}'"
                    raise ImgGenGenerationError(msg)

                # Decode base64 once and detect file type and dimensions
                image_bytes = base64.b64decode(first_base64)
                file_type = detect_file_type_from_bytes(image_bytes)
                image_format = ImageFormat.from_mime_type(
                    mime_type=file_type.mime,
                ).value
                with Image.open(io.BytesIO(image_bytes)) as pil_img:
                    width, height = pil_img.size
            else:
                msg = f"Could not parse image generation from Gateway response:\n{parsing_errors}"
                raise ImgGenGenerationError(msg)

            for image in images:
                base64_str = image.get("b64_json")
                if not isinstance(base64_str, str):
                    msg = f"No base64 image data received from model '{self.inference_model.model_id}'"
                    raise ImgGenGenerationError(msg)
                generated_images.append(
                    GeneratedImageRawDetails(
                        base64_str=base64_str,
                        size=ImageSize(width=width, height=height),
                        image_format=image_format,
                    ),
                )

        elif response_dict.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            # Handle FAL queue responses that require polling
            fal_poller = FalPoller()
            response_dict = await fal_poller.poll_queue_until_complete(response_dict=response_dict)

            for image in response_dict.get("images", []):
                url = image.get("url")
                if not isinstance(url, str):
                    msg = "Missing url field in image response"
                    raise ImgGenGenerationError(msg)
                fal_width = image.get("width")
                if not isinstance(fal_width, int):
                    msg = "Missing width field in image response"
                    raise ImgGenGenerationError(msg)
                fal_height = image.get("height")
                if not isinstance(fal_height, int):
                    msg = "Missing height field in image response"
                    raise ImgGenGenerationError(msg)
                content_type = image.get("content_type")
                if not isinstance(content_type, str):
                    msg = "Missing content_type field in image response"
                    raise ImgGenGenerationError(msg)
                generated_image = GeneratedImageRawDetails(
                    actual_url_or_prefixed_base64=url,
                    size=ImageSize(width=fal_width, height=fal_height),
                    mime_type=content_type,
                )
                generated_images.append(generated_image)
        else:
            msg = f"Unexpected response from model '{self.inference_model.model_id}' has no 'data' or 'images' key"
            raise ImgGenGenerationError(msg)

        return generated_images
