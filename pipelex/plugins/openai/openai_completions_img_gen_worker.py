from typing import TYPE_CHECKING, Any, cast

import openai
from openai import APIConnectionError, BadRequestError, NotFoundError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base64_utils import extract_base64_str_from_base64_url_if_possible
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage
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
        if img_gen_job.job_params.aspect_ratio != AspectRatio.SQUARE:
            msg = f"OpenAI Completions ImgGen worker only supports square images. Aspect ratio: {img_gen_job.job_params.aspect_ratio}"
            raise ImgGenParameterError(msg)
        img_gen_prompt_text = img_gen_job.img_gen_prompt.positive_text
        messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": img_gen_prompt_text}]
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
        except APIConnectionError as api_connection_error:
            msg = f"ImgGen API connection error: {api_connection_error}"
            raise ImgGenGenerationError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"ImgGen bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise ImgGenGenerationError(msg) from bad_request_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        actual_url: str | None = None
        base64_str: str | None = None
        base64_extracted_mime_type: str | None = None
        if (content := openai_message.content) and content.startswith("http"):
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
        return GeneratedImageRawDetails(
            actual_url=actual_url,
            base64_str=base64_str,
            size=ImageSize(width=1024, height=1024),
            mime_type=base64_extracted_mime_type,
            image_format=image_format,
        )

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
