from abc import abstractmethod

from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from openai.types.completion_usage import CompletionUsage
from typing_extensions import override

from pipelex.cogt.image.prompt_image import PromptImage, PromptImageDetail
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict
from pipelex.plugins.plugin_factory_abstract import PluginFactoryAbstract


class OpenAIFactoryAbstract(PluginFactoryAbstract):
    """Protocol defining the interface for OpenAI-compatible message factories."""

    @abstractmethod
    async def make_simple_messages(self, llm_job: LLMJob) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""

    @abstractmethod
    async def make_image_url_obj(self, prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
        """Creates an OpenAI-typed ImageURL object from a PromptImage."""

    @abstractmethod
    def make_nb_tokens_by_category(self, usage: CompletionUsage) -> NbTokensByCategoryDict:
        """Extracts token usage statistics from a CompletionUsage object."""

    @override
    def make_extra_headers(self, llm_job: LLMJob, output_desc: str) -> dict[str, str]:
        return {}
