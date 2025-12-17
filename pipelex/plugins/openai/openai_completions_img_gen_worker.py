from typing import TYPE_CHECKING, Any, cast

import openai
from openai import APIConnectionError, BadRequestError, NotFoundError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol

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
            raise LLMModelNotFoundError(msg) from not_found_error
        except APIConnectionError as api_connection_error:
            msg = f"ImgGen API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"ImgGen bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        url: str | None = None
        if (content := openai_message.content) and content.startswith("http"):
            url = openai_message.content
        elif hasattr(openai_message, "content_blocks"):
            content_blocks = cast("list[dict[str, Any]]", openai_message.content_blocks)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            for part in content_blocks:
                if part.get("type") == "image_url":
                    if image_url := part.get("image_url"):
                        if the_url := image_url.get("url"):
                            url = the_url
                            break
        if not url:
            msg = f"OpenAI response has no image. Model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)
        # TODO: raise if other size than 1024x1024 was requested
        return GeneratedImageRawDetails(
            actual_url=url,
            width=1024,
            height=1024,
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
