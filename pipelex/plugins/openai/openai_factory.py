import openai
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from openai.types.completion_usage import CompletionUsage
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImageDetail, PromptImagePath, PromptImageTypedBase64, PromptImageUrl
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_factory_abstract import OpenAIFactoryAbstract
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from pipelex.types import StrEnum


class OpenAIFactoryError(CogtError):
    pass


class OpenAISdkVariant(StrEnum):
    AZURE_OPENAI = "azure_openai"
    AZURE_OPENAI_RESPONSES = "azure_openai_responses"
    OPENAI = "openai"
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_ALT_IMG_GEN = "openai_alt_img_gen"


class AzureExtraField(StrEnum):
    API_VERSION = "api_version"


class OpenAIFactory(OpenAIFactoryAbstract):
    def __init__(self, is_http_url_enabled: bool):
        super().__init__()
        self.is_http_url_enabled = is_http_url_enabled

    @classmethod
    def make_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncClient:
        try:
            sdk_variant = OpenAISdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by OpenAIFactory"
            raise OpenAIFactoryError(msg) from exc

        # We have a workaround here:
        # OpenAI can be used without any API key (for instance when pointing to local Ollama) but the SDK,
        # as it is, raises if there is not API key (api_key is None and there is not env var).
        # But it works fine with an empty string.
        api_key = backend.api_key or ""

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case OpenAISdkVariant.AZURE_OPENAI | OpenAISdkVariant.AZURE_OPENAI_RESPONSES:
                log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                if backend.endpoint is None:
                    msg = "Azure OpenAI endpoint is not set"
                    raise OpenAIFactoryError(msg)
                the_client = openai.AsyncAzureOpenAI(
                    azure_endpoint=backend.endpoint,
                    api_key=api_key,
                    api_version=backend.get_extra_config(AzureExtraField.API_VERSION),
                )
            case OpenAISdkVariant.OPENAI | OpenAISdkVariant.OPENAI_RESPONSES:
                log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=backend.endpoint,
                )
            case OpenAISdkVariant.OPENAI_ALT_IMG_GEN:
                log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=backend.endpoint,
                )

        return the_client

    @override
    @override
    async def make_simple_messages(
        self,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        user_contents: list[ChatCompletionContentPartParam] = []
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))
        # TODO: confirm that we can prompt without user_contents, for instance if we have only images,
        # otherwise consider using a default user_content
        if user_prompt_text := llm_prompt.user_text:
            user_part_text = ChatCompletionContentPartTextParam(text=user_prompt_text, type="text")
            user_contents.append(user_part_text)
        if llm_prompt.user_images:
            detail = llm_job.job_params.image_detail or PromptImageDetail.AUTO
            prepped_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=self.is_http_url_enabled)
            for prepped_image in prepped_images:
                if isinstance(prepped_image, str):
                    url = prepped_image
                else:
                    assert isinstance(prepped_image, PromptImageTypedBase64)
                    url = PromptImageFactory.make_base_64_url_from_prompt_image_typed_base64(prompt_image=prepped_image)

                image_url_obj = ImageURL(url=url, detail=detail.as_openai_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @override
    async def make_image_url_obj(self, prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
        if detail is None:
            detail = PromptImageDetail.AUTO
        if isinstance(prompt_image, PromptImageUrl):
            url = prompt_image.url
            image_url_obj = ImageURL(url=url, detail=detail.as_openai_detail)
        elif isinstance(prompt_image, PromptImageBase64):
            # TODO: manage image type
            url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.base_64.decode('utf-8')}"
            image_url_obj = ImageURL(url=url_with_bytes, detail=detail.as_openai_detail)
        elif isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(path=prompt_image.file_path)
            return await self.make_image_url_obj(prompt_image=PromptImageBase64(base_64=image_bytes), detail=detail)
        else:
            msg = f"prompt_image of type {type(prompt_image)} is not supported"
            raise LLMPromptParameterError(msg)
        return image_url_obj

    @override
    def make_nb_tokens_by_category(self, usage: CompletionUsage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.prompt_tokens,
            TokenCategory.OUTPUT: usage.completion_tokens,
        }
        if prompt_tokens_details := usage.prompt_tokens_details:
            nb_tokens_by_category[TokenCategory.INPUT_AUDIO] = prompt_tokens_details.audio_tokens or 0
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = prompt_tokens_details.cached_tokens or 0
        if completion_tokens_details := usage.completion_tokens_details:
            nb_tokens_by_category[TokenCategory.OUTPUT_AUDIO] = completion_tokens_details.audio_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = completion_tokens_details.reasoning_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_ACCEPTED_PREDICTION] = completion_tokens_details.accepted_prediction_tokens or 0
            nb_tokens_by_category[TokenCategory.OUTPUT_REJECTED_PREDICTION] = completion_tokens_details.rejected_prediction_tokens or 0
        return nb_tokens_by_category
