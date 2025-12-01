from typing import Protocol, runtime_checkable

from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from openai.types.completion_usage import CompletionUsage

from pipelex.cogt.image.prompt_image import PromptImage, PromptImageDetail
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict


@runtime_checkable
class OpenAIFactoryProtocol(Protocol):
    """Protocol defining the interface for OpenAI-compatible message factories."""

    async def make_simple_messages(self, llm_job: LLMJob) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        ...

    async def make_image_url_obj(self, prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
        """Creates an OpenAI-typed ImageURL object from a PromptImage."""
        ...

    def make_nb_tokens_by_category(self, usage: CompletionUsage) -> NbTokensByCategoryDict:
        """Extracts token usage statistics from a CompletionUsage object."""
        ...
