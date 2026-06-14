import base64
from typing import TYPE_CHECKING, Any, cast

import openai
from openai import (
    APIConnectionError,
    APIStatusError,
)
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_openai_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base64_utils import extract_base64_str_from_base64_url_if_possible
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from openai.types.images_response import ImagesResponse, Usage


class OpenAIImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided ImgGen sdk_instance is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client = sdk_instance

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
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)

        args_dict = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
            model_name=self.inference_model.name,
        )

        images_response: ImagesResponse
        try:
            if image_arg := args_dict.get("image"):
                args_dict["image"] = self._convert_image_data_urls_for_openai_sdk(image_arg=image_arg)
                if args_dict.pop("moderation", None) is not None:
                    log.warning("OpenAI images.edit does not accept 'moderation'; dropping the kwarg")
                images_response = cast("ImagesResponse", await self.openai_client.images.edit(**args_dict))
            else:
                images_response = cast("ImagesResponse", await self.openai_client.images.generate(**args_dict))
        except (APIStatusError, APIConnectionError) as sdk_exc:
            metadata = extract_openai_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.IMG_GEN,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if not images_response.data:
            msg = "No result from OpenAI"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="OpenAI returned no image — try rephrasing the prompt or using a different model",
                ),
                provider_metadata=None,
            )

        response_output_format: str | None = images_response.output_format
        size: str | None = images_response.size or self._get_requested_size(args_dict=args_dict)
        if not size:
            msg = "No size received from OpenAI"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="OpenAI returned an image without size metadata — try a different model",
                ),
                provider_metadata=None,
            )
        size_split = size.split("x")
        if len(size_split) != 2:
            msg = f"Size from OpenAI is not a valid size: '{size}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="OpenAI returned a malformed image size — try a different model",
                ),
                provider_metadata=None,
            )
        width_str, height_str = size_split
        width = int(width_str)
        height = int(height_str)

        usage: Usage | None = images_response.usage
        if not usage:
            msg = "No usage received from OpenAI"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="OpenAI returned an image without usage metadata — try a different model",
                ),
                provider_metadata=None,
            )

        if img_gen_tokens_usage := img_gen_job.job_report.img_gen_tokens_usage:
            nb_tokens: NbTokensByCategoryDict = {
                TokenCategory.INPUT: usage.input_tokens,
                TokenCategory.OUTPUT: usage.output_tokens,
            }
            img_gen_tokens_usage.nb_tokens_by_category = nb_tokens

        generated_images: list[GeneratedImageRawDetails] = []
        for image_data in images_response.data:
            base64_str = image_data.b64_json
            if not base64_str:
                msg = "No base64 image data received from OpenAI"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail="OpenAI returned no image data — try rephrasing the prompt or using a different model",
                    ),
                    provider_metadata=None,
                )

            image_format = response_output_format
            if image_format is None:
                image_bytes = base64.b64decode(base64_str)
                file_type = detect_file_type_from_bytes(image_bytes)
                image_format = ImageFormat.from_mime_type(mime_type=file_type.mime).value

            generated_images.append(
                GeneratedImageRawDetails(
                    base64_str=base64_str,
                    size=ImageSize(width=width, height=height),
                    image_format=image_format,
                ),
            )
        return generated_images

    @staticmethod
    def _convert_image_data_urls_for_openai_sdk(image_arg: Any) -> list[tuple[str, bytes, str]]:
        """Convert shared GPT Image data URLs into the OpenAI SDK's multipart file tuples."""
        if not isinstance(image_arg, list):
            msg = f"OpenAI image edit expected a list of image data URLs, got '{type(image_arg).__name__}'"
            raise ImgGenParameterError(msg)

        image_data_urls = cast("list[Any]", image_arg)
        image_files: list[tuple[str, bytes, str]] = []
        for index, image_data_url in enumerate(image_data_urls):
            if not isinstance(image_data_url, str):
                msg = f"OpenAI image edit expected image #{index} to be a data URL, got '{type(image_data_url).__name__}'"
                raise ImgGenParameterError(msg)
            extracted = extract_base64_str_from_base64_url_if_possible(possibly_base64_url=image_data_url)
            if extracted is None:
                msg = "OpenAI image edit expected base64 data URLs from the shared image argument factory"
                raise ImgGenParameterError(msg)
            base64_str, mime_type = extracted
            file_extension = mime_type.split("/", 1)[1].replace("jpeg", "jpg")
            image_bytes = base64.b64decode(base64_str)
            image_files.append((f"image_{index}.{file_extension}", image_bytes, mime_type))
        return image_files

    @staticmethod
    def _get_requested_size(args_dict: dict[str, Any]) -> str | None:
        requested_size = args_dict.get("size")
        if isinstance(requested_size, str):
            return requested_size
        return None
