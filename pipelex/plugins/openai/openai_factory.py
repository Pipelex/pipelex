from typing import Any, Dict, List, Optional

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

from pipelex import log
from pipelex.cogt.exceptions import CogtError, LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from pipelex.types import StrEnum


class OpenAIFactoryError(CogtError):
    pass


class OpenAISdkVariant(StrEnum):
    AZURE_OPENAI = "azure_openai"
    OPENAI = "openai"


class AzureExtraField(StrEnum):
    API_VERSION = "api_version"


class OpenAIFactory:
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

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case OpenAISdkVariant.AZURE_OPENAI:
                log.debug(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                if backend.endpoint is None:
                    msg = "Azure OpenAI endpoint is not set"
                    raise OpenAIFactoryError(msg)
                the_client = openai.AsyncAzureOpenAI(
                    azure_endpoint=backend.endpoint,
                    api_key=backend.api_key,
                    api_version=backend.get_extra_config(AzureExtraField.API_VERSION),
                )

            case OpenAISdkVariant.OPENAI:
                log.debug(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=backend.api_key,
                    base_url=backend.endpoint,
                )

        return the_client

    @classmethod
    def make_simple_messages(
        cls,
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
            for prompt_image in llm_prompt.user_images:
                openai_image_url = cls.make_openai_image_url(prompt_image=prompt_image)
                image_param = ChatCompletionContentPartImageParam(image_url=openai_image_url, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @classmethod
    def make_responses_input(
        cls,
        llm_job: LLMJob,
        llm_engine: LLMEngine,
    ) -> Dict[str, Any]:
        """
        Build the input payload for the OpenAI Responses API from our prompt and params.
        This is compatible with the OpenAI tools/connectors quickstart when using responses.create.
        """
        llm_prompt = llm_job.llm_prompt
        input_value: Any
        if llm_prompt.user_text and not llm_prompt.user_images:
            input_value = llm_prompt.user_text
        else:
            # Build simple multi-part input with text first, images ignored for now
            parts: List[Dict[str, Any]] = []
            if llm_prompt.user_text:
                parts.append({"type": "input_text", "text": llm_prompt.user_text})
            # Future: map PromptImage to Responses API input_image blocks
            input_value = parts if parts else ""

        payload: Dict[str, Any] = {
            "model": llm_engine.llm_id,
            "input": input_value,
        }

        params = llm_job.job_params
        if params.max_tokens is not None:
            payload["max_output_tokens"] = params.max_tokens
        if params.seed is not None:
            payload["seed"] = params.seed
        # temperature is supported on some models under responses
        payload["temperature"] = 1 if llm_engine.llm_model.llm_family.name.startswith("O_") else params.temperature

        # System prompt as responses "instructions"
        if llm_prompt.system_text:
            payload["instructions"] = llm_prompt.system_text

        # Tools / connectors
        if params.openai_tools:
            payload["tools"] = params.openai_tools
        if params.openai_tool_choice is not None:
            payload["tool_choice"] = params.openai_tool_choice
        if params.openai_parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = params.openai_parallel_tool_calls
        if params.openai_response_format is not None:
            payload["response_format"] = params.openai_response_format

        return payload

    @classmethod
    def make_openai_image_url(cls, prompt_image: PromptImage) -> ImageURL:
        if isinstance(prompt_image, PromptImageUrl):
            url = prompt_image.url
            openai_image_url = ImageURL(url=url, detail="high")
        elif isinstance(prompt_image, PromptImageBase64):
            # TODO: manage image type
            url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.base_64.decode('utf-8')}"
            openai_image_url = ImageURL(url=url_with_bytes, detail="high")
        elif isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(path=prompt_image.file_path)
            return cls.make_openai_image_url(PromptImageBase64(base_64=image_bytes))
        else:
            msg = f"prompt_image of type {type(prompt_image)} is not supported"
            raise LLMPromptParameterError(msg)
        return openai_image_url

    @staticmethod
    def make_openai_error_info(exception: Exception) -> str:
        error_mapping: dict[type, str] = {
            openai.BadRequestError: "OpenAI API request was invalid.",
            openai.InternalServerError: "OpenAI is having trouble. Please try again later.",
            openai.RateLimitError: "OpenAI API request exceeded rate limit.",
            openai.AuthenticationError: "OpenAI API request was not authorized.",
            openai.PermissionDeniedError: "OpenAI API request was not permitted.",
            openai.NotFoundError: "Requested resource not found.",
            openai.APITimeoutError: "OpenAI API request timed out.",
            openai.APIConnectionError: "OpenAI API request failed to connect.",
            openai.APIError: "OpenAI API returned an API Error.",
        }
        return error_mapping.get(type(exception), "An unexpected error occurred with the OpenAI API.")

    # reference:
    # https://help.openai.com/en/articles/5247780-using-logit-bias-to-define-token-probability
    # https://platform.openai.com/tokenizer
    @staticmethod
    def make_logit_bias(nb_items: int, weight: int = 100) -> dict[str, int]:
        logit_bias = {str(item): weight for item in range(15, 15 + nb_items + 1)}
        log.debug(f"logit_bias: {logit_bias}")
        return logit_bias

    @staticmethod
    def make_nb_tokens_by_category(usage: CompletionUsage) -> NbTokensByCategoryDict:
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
