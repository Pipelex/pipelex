from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_factory import OpenAIFactory

if TYPE_CHECKING:
    import openai
    from openai.types.responses import (
        ResponseInputImageParam,
        ResponseInputItemParam,
        ResponseInputMessageContentListParam,
        ResponseInputTextParam,
        ResponseUsage,
    )

    from pipelex.cogt.image.prompt_image import PromptImage
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.plugins.openai.openai_factory_protocol import OpenAIFactoryProtocol
    from pipelex.plugins.plugin_sdk_registry import Plugin


class OpenAIResponsesFactory:
    def __init__(self, openai_factory: OpenAIFactoryProtocol | None = None):
        self.openai_factory: OpenAIFactoryProtocol = openai_factory or OpenAIFactory()

    @classmethod
    def make_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        return OpenAIFactory.make_openai_client(
            plugin=plugin,
            backend=backend,
        )

    async def make_input_items(self, llm_job: LLMJob) -> list[ResponseInputItemParam]:
        """Build Response API input items from a standard LLM job prompt."""
        llm_prompt = llm_job.llm_prompt
        input_items: list[ResponseInputItemParam] = []

        user_contents: ResponseInputMessageContentListParam = []
        if llm_prompt.user_text:
            text_content: ResponseInputTextParam = {"type": "input_text", "text": llm_prompt.user_text}
            user_contents.append(text_content)

        for prompt_image in llm_prompt.user_images:
            image_content = await self._make_image_content(prompt_image=prompt_image, detail=llm_job.job_params.image_detail)
            user_contents.append(image_content)

        if not user_contents:
            msg = "LLM prompt must include text or images for the user input when using the OpenAI Responses API"
            raise LLMPromptParameterError(msg)

        input_items.append(
            {
                "role": "user",
                "content": user_contents,
            }
        )
        return input_items

    async def _make_image_content(self, prompt_image: PromptImage, detail: PromptImageDetail | None) -> ResponseInputImageParam:
        if detail is None:
            detail = PromptImageDetail.AUTO
        image_url_obj = await self.openai_factory.make_image_url_obj(prompt_image=prompt_image, detail=detail)
        return {"type": "input_image", "image_url": image_url_obj["url"], "detail": detail.as_openai_detail}

    def make_nb_tokens_by_category(self, usage: ResponseUsage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.input_tokens,
            TokenCategory.OUTPUT: usage.output_tokens,
        }
        if usage.input_tokens_details:
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = usage.input_tokens_details.cached_tokens
        if usage.output_tokens_details:
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = usage.output_tokens_details.reasoning_tokens
        return nb_tokens_by_category
