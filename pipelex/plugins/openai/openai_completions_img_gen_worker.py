from typing import TYPE_CHECKING, Any, cast

import openai
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, NotFoundError, RateLimitError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    is_content_policy_violation,
    is_quota_exhaustion_openai,
)
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base64_utils import extract_base64_str_from_base64_url_if_possible
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl
from pipelex.urls import URLs

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage
    from openai.types.chat.chat_completion_content_part_param import ChatCompletionContentPartParam
    from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam


class OpenAICompletionsImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        openai_completions_factory: OpenAICompletionsFactory,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided ImgGen sdk_instance is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client = sdk_instance
        self.openai_completions_factory = openai_completions_factory

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        log.debug(f"Generating image with model: {self.inference_model.tag}")
        image_format: ImageFormat | None = None
        if self.inference_model.backend_name == "pipelex_gateway":
            if img_gen_job.job_params.output_format and not img_gen_job.job_params.output_format.is_png:
                msg = (
                    f"Completions ImgGen worker for Pipelex Gateway only supports PNG output format. "
                    f"Requested output format: {img_gen_job.job_params.output_format}"
                )
                raise ImgGenParameterError(msg)
            image_format = ImageFormat.PNG
        if self.inference_model.backend_name == "blackboxai":
            if img_gen_job.job_params.output_format and not img_gen_job.job_params.output_format.is_jpeg:
                msg = (
                    f"Completions ImgGen worker for BlackboxAI only supports JPEG output format. "
                    f"Requested output format: {img_gen_job.job_params.output_format}"
                )
                raise ImgGenParameterError(msg)
            image_format = ImageFormat.JPEG

        # Build message content with optional input images
        messages = await self._build_messages_with_images(img_gen_job)

        try:
            extra_headers, extra_body = self.openai_completions_factory.make_extras(
                inference_model=self.inference_model, inference_job=img_gen_job, output_desc=InferenceOutputType.IMAGE
            )
            response = await self.openai_client.chat.completions.create(
                model=self.inference_model.model_id,
                messages=messages,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
        except NotFoundError as not_found_error:
            msg = f"ImgGen model or deployment not found:\n{self.inference_model.desc}\nmodel: {self.inference_model.desc}\n{not_found_error}"
            raise ImgGenModelNotFoundError(message=msg, model_handle=self.inference_model.name) from not_found_error
        except RateLimitError as rate_limit_error:
            error_message = str(rate_limit_error)
            if is_quota_exhaustion_openai(error_message):
                msg = f"OpenAI quota exhausted for model '{self.inference_model.desc}': {rate_limit_error}"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=UserAction(
                        kind=UserActionKind.UNKNOWN,
                        detail=f"Your OpenAI account has exceeded its quota — check billing at {URLs.openai_billing}",
                    ),
                ) from rate_limit_error
            msg = f"OpenAI rate limit exceeded for model '{self.inference_model.desc}': {rate_limit_error}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.UNKNOWN,
                    detail="Rate limited by OpenAI — the system will retry automatically",
                ),
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
                    user_action=UserAction(
                        kind=UserActionKind.UNKNOWN,
                        detail="Content was rejected by safety filters — revise the prompt",
                    ),
                ) from bad_request_error
            msg = f"ImgGen bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.CONTENT) from bad_request_error
        except AuthenticationError as authentication_error:
            msg = f"ImgGen authentication error: {authentication_error}"
            raise ImgGenGenerationError(msg, error_category=InferenceErrorCategory.CONFIGURATION) from authentication_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        actual_url: str | None = None
        base64_str: str | None = None
        base64_extracted_mime_type: str | None = None
        if hasattr(openai_message, "images"):
            images = cast("list[dict[str, Any]]", openai_message.images)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            if images:
                image_obj = images[0]
                if image_url := image_obj.get("image_url"):
                    if the_url := image_url.get("url"):
                        extracted = extract_base64_str_from_base64_url_if_possible(possibly_base64_url=the_url)
                        if not extracted:
                            msg = "No base64 string found in ImgGenCompletions response message (images)"
                            raise ImgGenGenerationError(msg)
                        base64_str, base64_extracted_mime_type = extracted
        elif (content := openai_message.content) and content.startswith("http"):
            # OpenAI response message is a URL, this happens with blackboxai and pipelex_gateway which have a fixed output format.
            # Otherwise we won't know what format the image is in.
            if image_format is None:
                msg = (
                    f"OpenAI response message is a URL but output_format is not set. This shouldn't be possible. "
                    f"This response should only happen when using backend 'blackboxai' or 'pipelex_gateway'. "
                    f"Backend is: '{self.inference_model.backend_name}'"
                )
                raise ImgGenParameterError(msg)
            actual_url = openai_message.content
        elif hasattr(openai_message, "content_blocks"):
            content_blocks = cast("list[dict[str, Any]]", openai_message.content_blocks)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            for part in content_blocks:
                if part.get("type") == "image_url":
                    if image_url := part.get("image_url"):
                        if the_url := image_url.get("url"):
                            extracted = extract_base64_str_from_base64_url_if_possible(possibly_base64_url=the_url)
                            if not extracted:
                                msg = "No base64 string found in ImgGenCompletions response message"
                                raise ImgGenGenerationError(msg)
                            base64_str, base64_extracted_mime_type = extracted
                            break
        if not base64_str and not actual_url:
            msg = f"ImgGenCompletions response has no image. Model: {self.inference_model.desc}"
            raise ImgGenGenerationError(msg)

        if (img_gen_tokens_usage := img_gen_job.job_report.img_gen_tokens_usage) and (usage := response.usage):
            img_gen_tokens_usage.nb_tokens_by_category = self.openai_completions_factory.make_nb_tokens_by_category(usage=usage)

        # Size is None because the API doesn't return it. We now support various aspect ratios,
        # but detecting the size here (e.g., via Pillow) is left to downstream consumers if needed.
        return GeneratedImageRawDetails(
            actual_url=actual_url,
            base64_str=base64_str,
            size=None,
            mime_type=base64_extracted_mime_type,
            image_format=image_format,
        )

    async def _build_messages_with_images(
        self,
        img_gen_job: ImgGenJob,
    ) -> "list[ChatCompletionMessageParam]":
        """Build chat messages with optional input images for image-to-image generation.

        For models that support image inputs via the chat completions API (e.g., Gemini),
        images are included as content parts alongside the text prompt.
        """
        img_gen_prompt = img_gen_job.img_gen_prompt
        img_gen_prompt_text = img_gen_prompt.positive_text

        # If no input images, return simple text message
        if not img_gen_prompt.input_images:
            return [{"role": "user", "content": img_gen_prompt_text}]

        # Build content parts with images
        user_contents: list[ChatCompletionContentPartParam] = []

        # Add text prompt first
        user_contents.append({"type": "text", "text": img_gen_prompt_text})

        # Prepare and add images
        prepped_images = await prep_prompt_images(
            prompt_images=img_gen_prompt.input_images,
            is_http_url_enabled=True,
        )
        for prepped_image in prepped_images:
            if isinstance(prepped_image, PreparedFileBase64):
                user_contents.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": prepped_image.as_data_url()},
                    }
                )
            elif isinstance(prepped_image, PreparedFileHttpUrl):
                user_contents.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": prepped_image.url},
                    }
                )
            else:
                msg = f"Unexpected PreparedFile type: {type(prepped_image).__name__}"
                raise ImgGenParameterError(msg)

        return [{"role": "user", "content": user_contents}]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        if nb_images > 1:
            msg = f"The image genration backend '{self.inference_model.desc}' can't generate multiple images at once: {nb_images}"
            raise NotImplementedError(msg)
        return [await self._gen_image(img_gen_job=img_gen_job)]
