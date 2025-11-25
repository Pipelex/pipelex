from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImagePath, PromptImageUrl
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_factory import OpenAIFactory

if TYPE_CHECKING:
    import openai
    from openai.types.chat.chat_completion_content_part_image_param import ImageURL
    from openai.types.responses import (
        ResponseInputImageParam,
        ResponseInputItemParam,
        ResponseInputMessageContentListParam,
        ResponseInputTextParam,
        ResponseUsage,
    )

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.plugins.plugin_sdk_registry import Plugin


class OpenAIResponsesFactory:
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

    @classmethod
    def make_input_items(cls, llm_job: LLMJob) -> list[ResponseInputItemParam]:
        """Build Response API input items from a standard LLM job prompt."""
        llm_prompt = llm_job.llm_prompt
        input_items: list[ResponseInputItemParam] = []

        user_contents: ResponseInputMessageContentListParam = []
        if llm_prompt.user_text:
            text_content: ResponseInputTextParam = {"type": "input_text", "text": llm_prompt.user_text}
            user_contents.append(text_content)

        for prompt_image in llm_prompt.user_images:
            image_content = cls._make_image_content(prompt_image=prompt_image)
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

    @classmethod
    def _make_image_content(cls, prompt_image: PromptImage) -> ResponseInputImageParam:
        openai_image_url = cls._make_openai_image_url(prompt_image=prompt_image)
        detail = openai_image_url.get("detail") or "high"
        return {"type": "input_image", "image_url": openai_image_url["url"], "detail": detail}

    @classmethod
    def _make_openai_image_url(cls, prompt_image: PromptImage) -> ImageURL:
        if isinstance(prompt_image, PromptImageUrl):
            url = prompt_image.url
            openai_image_url: ImageURL = {"url": url, "detail": "high"}
        elif isinstance(prompt_image, PromptImageBase64):
            url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.base_64.decode('utf-8')}"
            openai_image_url = {"url": url_with_bytes, "detail": "high"}
        elif isinstance(prompt_image, PromptImagePath):
            openai_image_url = OpenAIFactory.make_openai_image_url(prompt_image=prompt_image)
        else:
            msg = f"prompt_image of type {type(prompt_image)} is not supported"
            raise LLMPromptParameterError(msg)
        return openai_image_url

    @staticmethod
    def make_nb_tokens_by_category(usage: ResponseUsage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.input_tokens,
            TokenCategory.OUTPUT: usage.output_tokens,
        }
        if usage.input_tokens_details:
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = usage.input_tokens_details.cached_tokens
        if usage.output_tokens_details:
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = usage.output_tokens_details.reasoning_tokens
        return nb_tokens_by_category
