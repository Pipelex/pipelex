# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, List

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
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_report import NbTokensByCategoryDict
from pipelex.cogt.llm.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.hub import get_secrets_provider
from pipelex.tools.misc.base_64 import load_binary_as_base64


class OpenAIFactoryError(CogtError):
    pass


class OpenAIFactory:
    @classmethod
    def make_openai_client(cls, llm_platform: LLMPlatform) -> openai.AsyncClient:
        the_client: openai.AsyncOpenAI

        match llm_platform:
            case LLMPlatform.AZURE_OPENAI:
                azure_openai_config = get_config().cogt.llm_config.azure_openai_config
                api_key = azure_openai_config.get_api_key(secrets_provider=get_secrets_provider())
                azure_endpoint = azure_openai_config.api_endpoint
                api_version = azure_openai_config.api_version

                log.verbose(f"Making AsyncAzureOpenAI client with endpoint: {azure_endpoint}, api_version: {api_version}")
                the_client = openai.AsyncAzureOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                    api_version=api_version,
                )
            case LLMPlatform.PERPLEXITY:
                perplexity_config = get_config().cogt.llm_config.perplexity_config
                api_key = perplexity_config.get_api_key(secrets_provider=get_secrets_provider())
                endpoint = perplexity_config.api_endpoint

                log.verbose(f"Making perplexity AsyncOpenAI client with endpoint: {endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=endpoint,
                )
            case LLMPlatform.OPENAI:
                openai_openai_config = get_config().cogt.llm_config.openai_openai_config
                api_key = openai_openai_config.get_api_key(secrets_provider=get_secrets_provider())
                the_client = openai.AsyncOpenAI(api_key=api_key)
            case LLMPlatform.VERTEXAI_OPENAI:
                vertexai_config = get_config().cogt.llm_config.vertexai_config
                project_id = vertexai_config.project_id
                region = vertexai_config.region
                api_key = vertexai_config.get_api_key()
                endpoint = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{region}/endpoints/openapi"

                log.verbose(f"Making vertex AsyncOpenAI client with endpoint: {endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=endpoint,
                )
            case _:
                raise OpenAIFactoryError(f"Platform '{llm_platform}' is not supported by this factory '{cls.__name__}'")

        return the_client

    @classmethod
    def make_simple_messages(
        cls,
        llm_job: LLMJob,
        llm_engine: LLMEngine,
    ) -> List[ChatCompletionMessageParam]:
        """
        Makes a list of messages with a system message (if provided) and followed by a user message.
        """
        llm_prompt = llm_job.llm_prompt
        messages: List[ChatCompletionMessageParam] = []
        user_contents: List[ChatCompletionContentPartParam] = []
        if llm_engine.llm_model.is_system_prompt_supported and (system_content := llm_prompt.system_text):
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
    def make_openai_image_url(cls, prompt_image: PromptImage) -> ImageURL:
        if isinstance(prompt_image, PromptImageUrl):
            url = prompt_image.url
            openai_image_url = ImageURL(url=url, detail="high")
        elif isinstance(prompt_image, PromptImageBytes):
            # TODO: manage image type
            url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.b64_image_bytes.decode('utf-8')}"
            openai_image_url = ImageURL(url=url_with_bytes, detail="high")
        elif isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(path=prompt_image.file_path)
            return cls.make_openai_image_url(PromptImageBytes(b64_image_bytes=image_bytes))
        else:
            raise ValueError(f"prompt_image of type {type(prompt_image)} is not supported")
        return openai_image_url

    @staticmethod
    def make_openai_error_info(exception: Exception) -> str:
        error_mapping: Dict[type, str] = {
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
        error_info = error_mapping.get(type(exception), "An unexpected error occurred with the OpenAI API.")
        return error_info

    # reference:
    # https://help.openai.com/en/articles/5247780-using-logit-bias-to-define-token-probability
    # https://platform.openai.com/tokenizer
    @staticmethod
    def make_logit_bias(nb_items: int, weight: int = 100) -> dict[str, int]:
        logit_bias = {str(k): weight for k in range(15, 15 + nb_items + 1)}
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
