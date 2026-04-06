from typing import TYPE_CHECKING, Any

import openai
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, NotFoundError, RateLimitError
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import (
    is_content_policy_violation,
    is_quota_exhaustion_openai,
)
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_img_gen_factory import OpenAIImgGenFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.urls import URLs

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
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        image_size, width, height = OpenAIImgGenFactory.image_size_for_gpt_image_1(aspect_ratio=img_gen_job.job_params.aspect_ratio)
        output_format = OpenAIImgGenFactory.output_format_for_gpt_image_1(output_format=img_gen_job.job_params.output_format)
        moderation = OpenAIImgGenFactory.moderation_for_gpt_image_1(is_moderated=img_gen_job.job_params.is_moderated)
        background = OpenAIImgGenFactory.background_for_gpt_image_1(background=img_gen_job.job_params.background)
        quality = OpenAIImgGenFactory.quality_for_gpt_image_1(quality=img_gen_job.job_params.quality or Quality.LOW)
        output_compression = OpenAIImgGenFactory.output_compression_for_gpt_image_1()
        try:
            images_response: ImagesResponse = await self.openai_client.images.generate(
                prompt=img_gen_job.img_gen_prompt.positive_text,
                model=self.inference_model.model_id,
                moderation=moderation,
                background=background,
                quality=quality,
                size=image_size,
                output_format=output_format,
                output_compression=output_compression,
                n=nb_images,
            )
        except NotFoundError as not_found_error:
            msg = f"ImgGen model or deployment not found: {self.inference_model.desc}: {not_found_error}"
            raise ImgGenModelNotFoundError(message=msg, model_handle=self.inference_model.name) from not_found_error
        except RateLimitError as rate_limit_error:
            error_message = str(rate_limit_error)
            if is_quota_exhaustion_openai(error_message):
                msg = f"OpenAI quota exhausted for model '{self.inference_model.desc}': {rate_limit_error}"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=f"Your OpenAI account has exceeded its quota — check billing at {URLs.openai_billing}",
                ) from rate_limit_error
            msg = f"OpenAI rate limit exceeded for model '{self.inference_model.desc}': {rate_limit_error}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action="Rate limited by OpenAI — the system will retry automatically",
            ) from rate_limit_error
        except APITimeoutError as timeout_error:
            msg = f"OpenAI API request timed out for model '{self.inference_model.desc}': {timeout_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.TRANSIENT) from timeout_error
        except APIConnectionError as api_connection_error:
            msg = f"ImgGen API connection error: {api_connection_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.TRANSIENT) from api_connection_error
        except BadRequestError as bad_request_error:
            error_message = str(bad_request_error)
            if is_content_policy_violation(error_message):
                msg = f"Content rejected by safety filters for model '{self.inference_model.desc}': {bad_request_error}"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action="Content was rejected by safety filters — revise the prompt",
                ) from bad_request_error
            msg = f"ImgGen bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.CONTENT) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"ImgGen authentication error: {authentication_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.CONFIGURATION) from authentication_error
        if not images_response.data:
            msg = "No result from OpenAI"
            raise ImgGenGenerationError(msg)

        response_output_format: str | None = images_response.output_format
        if response_output_format is None:
            msg = "No output format received from OpenAI"
            raise ImgGenGenerationError(msg)
        size: str | None = images_response.size
        if not size:
            msg = "No size received from OpenAI"
            raise ImgGenGenerationError(msg)
        size_split = size.split("x")
        if len(size_split) != 2:
            msg = f"Size from OpenAI is not a valid size: '{size}'"
            raise ImgGenGenerationError(msg)
        width_str, height_str = size_split
        width = int(width_str)
        height = int(height_str)

        usage: Usage | None = images_response.usage
        if not usage:
            msg = "No usage received from OpenAI"
            raise ImgGenGenerationError(msg)

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
                raise ImgGenGenerationError(msg)

            generated_images.append(
                GeneratedImageRawDetails(
                    base64_str=base64_str,
                    size=ImageSize(width=width, height=height),
                    image_format=response_output_format,
                ),
            )
        return generated_images
