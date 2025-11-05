import random
from typing import TYPE_CHECKING, Any

import openai
from openai import APIConnectionError, BadRequestError, NotFoundError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessage


class OpenAIImgGenAlternativeWorker(ImgGenWorkerAbstract):
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
    ) -> GeneratedImage:
        log.debug(f"Generating image with model: {self.inference_model.tag}")
        img_gen_prompt_text = img_gen_job.img_gen_prompt.positive_text
        messages = [{"role": "user", "content": img_gen_prompt_text}]
        seed = img_gen_job.job_params.seed or random.randint(0, 2**32 - 1)
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.inference_model.model_id,
                messages=messages,  # type: ignore[arg-type]
                seed=seed,
            )
        except NotFoundError as not_found_error:
            # TODO: record llm config so it can be displayed here
            msg = f"OpenAI model or deployment not found:\n{self.inference_model.desc}\nmodel: {self.inference_model.desc}\n{not_found_error}"
            raise LLMModelNotFoundError(msg) from not_found_error
        except APIConnectionError as api_connection_error:
            msg = f"OpenAI API connection error: {api_connection_error}"
            raise LLMCompletionError(msg) from api_connection_error
        except BadRequestError as bad_request_error:
            msg = f"OpenAI bad request error with model: {self.inference_model.desc}:\n{bad_request_error}"
            raise LLMCompletionError(msg) from bad_request_error

        openai_message: ChatCompletionMessage = response.choices[0].message
        response_text = openai_message.content
        if response_text is None:
            msg = f"OpenAI response message content is None: {response}\nmodel: {self.inference_model.desc}"
            raise LLMCompletionError(msg)
        return GeneratedImage(
            url=response_text,
            width=1024,
            height=1024,
        )

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        if nb_images > 1:
            msg = f"The image genration backend '{self.inference_model.desc}' can't generate multiple images at once: {nb_images}"
            raise NotImplementedError(msg)
        return [await self._gen_image(img_gen_job=img_gen_job)]
