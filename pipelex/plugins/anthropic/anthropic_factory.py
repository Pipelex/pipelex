import math
from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic, AsyncAnthropicBedrock
from anthropic.types import Usage
from anthropic.types.document_block_param import DocumentBlockParam
from anthropic.types.image_block_param import ImageBlockParam
from anthropic.types.message_param import MessageParam
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.uri.prepared_file import PreparedFile, PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from anthropic.types.text_block_param import TextBlockParam


class AnthropicFactoryError(CogtError):
    pass


class AnthropicSdkVariant(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK_ANTHROPIC = "bedrock_anthropic"


class AnthropicFactory:
    @staticmethod
    def make_anthropic_client(
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> AsyncAnthropic | AsyncAnthropicBedrock:
        try:
            sdk_variant = AnthropicSdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by AnthropicFactory"
            raise AnthropicFactoryError(msg) from exc

        match sdk_variant:
            case AnthropicSdkVariant.ANTHROPIC:
                return AsyncAnthropic(
                    api_key=backend.api_key,
                    base_url=backend.endpoint,
                )
            case AnthropicSdkVariant.BEDROCK_ANTHROPIC:
                aws_config = get_config().pipelex.aws_config
                aws_access_key_id, aws_secret_access_key, aws_region = aws_config.get_aws_access_keys()
                return AsyncAnthropicBedrock(
                    aws_secret_key=aws_secret_access_key,
                    aws_access_key=aws_access_key_id,
                    aws_region=aws_region,
                )

    @staticmethod
    def _make_image_block_param(prepped_image: PreparedFile) -> ImageBlockParam:
        """Convert a PreparedFile to an Anthropic ImageBlockParam."""
        image_block_param: ImageBlockParam
        match prepped_image:
            case PreparedFileBase64():
                image_block_param = {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": prepped_image.mime_type,  # type: ignore[typeddict-item]
                        "data": prepped_image.base64_data,
                    },  # pyright: ignore[reportAssignmentType]
                }
            case PreparedFileHttpUrl():
                image_block_param = {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": prepped_image.url,
                    },
                }
            case PreparedFileLocalPath():
                msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                raise TypeError(msg)
        return image_block_param

    @staticmethod
    def _make_document_block_param(prepped_document: PreparedFile, title: str | None = None) -> DocumentBlockParam:
        """Convert a PreparedFile to an Anthropic DocumentBlockParam."""
        document_block_param: DocumentBlockParam
        match prepped_document:
            case PreparedFileBase64():
                source_dict: dict[str, str] = {
                    "type": "base64",
                    "media_type": prepped_document.mime_type,
                    "data": prepped_document.base64_data,
                }
                document_block_param = {
                    "type": "document",
                    "source": source_dict,  # type: ignore[typeddict-item]
                }  # pyright: ignore[reportAssignmentType]
                if title:
                    document_block_param["title"] = title
            case PreparedFileHttpUrl():
                document_block_param = {
                    "type": "document",
                    "source": {
                        "type": "url",
                        "url": prepped_document.url,
                    },
                }  # pyright: ignore[reportAssignmentType]
                if title:
                    document_block_param["title"] = title
            case PreparedFileLocalPath():
                msg = "PreparedFileLocalPath is not supported for documents - should be converted to base64"
                raise TypeError(msg)
        return document_block_param

    @classmethod
    async def make_user_message(
        cls,
        llm_job: LLMJob,
    ) -> MessageParam:
        message: MessageParam
        content: list[TextBlockParam | ImageBlockParam | DocumentBlockParam] = []
        llm_prompt = llm_job.llm_prompt

        if user_text := llm_prompt.user_text:
            text_block_param: TextBlockParam = {
                "type": "text",
                "text": user_text,
            }
            content.append(text_block_param)
        if llm_prompt.user_images:
            prepped_user_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=False)
            for prepped_image in prepped_user_images:
                content.append(cls._make_image_block_param(prepped_image))
        if llm_prompt.user_documents:
            prepped_user_documents = await prep_prompt_documents(prompt_documents=llm_prompt.user_documents, is_http_url_enabled=False)
            for prepped_document in prepped_user_documents:
                content.append(cls._make_document_block_param(prepped_document))

        message = {
            "role": "user",
            "content": content,
        }

        return message

    # This creates a MessageParam disguised as a ChatCompletionMessageParam to please instructor type checking
    @classmethod
    def openai_typed_user_message(
        cls,
        user_content_txt: str,
        prepped_user_images: list[PreparedFile] | None = None,
        prepped_user_documents: list[tuple[PreparedFile, str | None]] | None = None,
    ) -> ChatCompletionMessageParam:
        text_block_param: TextBlockParam = {"type": "text", "text": user_content_txt}
        message: MessageParam

        content: list[TextBlockParam | ImageBlockParam | DocumentBlockParam] = []

        if prepped_user_images is not None:
            for prepped_image in prepped_user_images:
                content.append(cls._make_image_block_param(prepped_image))

        if prepped_user_documents is not None:
            for prepped_document, title in prepped_user_documents:
                content.append(cls._make_document_block_param(prepped_document, title=title))

        content.append(text_block_param)

        message = {
            "role": "user",
            "content": content,
        }

        return message  # type: ignore[return-value, valid-type] # pyright: ignore[reportReturnType]

    @classmethod
    async def make_simple_messages(
        cls,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))

        prepped_user_images: list[PreparedFile] | None
        if llm_prompt.user_images:
            prepped_user_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=False)
        else:
            prepped_user_images = None

        prepped_user_documents: list[tuple[PreparedFile, str | None]] | None
        if llm_prompt.user_documents:
            prepped_docs = await prep_prompt_documents(prompt_documents=llm_prompt.user_documents, is_http_url_enabled=False)
            prepped_user_documents = [(prepped_doc, None) for prepped_doc in prepped_docs]
        else:
            prepped_user_documents = None

        # Concatenation ####
        messages.append(
            cls.openai_typed_user_message(
                user_content_txt=llm_prompt.user_text or "",
                prepped_user_images=prepped_user_images,
                prepped_user_documents=prepped_user_documents,
            ),
        )
        return messages

    @staticmethod
    def make_nb_tokens_by_category(usage: Usage) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.input_tokens,
            TokenCategory.OUTPUT: usage.output_tokens,
        }
        return nb_tokens_by_category

    @staticmethod
    def make_nb_tokens_by_category_from_nb(nb_input: int, nb_output: int) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: nb_input,
            TokenCategory.OUTPUT: nb_output,
        }
        return nb_tokens_by_category

    @staticmethod
    def calculate_safe_max_tokens_for_timeout(timeout_seconds: int) -> int:
        """Calculate max_tokens that won't trigger SDK timeout protection.

        Formula: max_tokens = timeout_seconds * 128000 / 3600
        Based on SDK heuristic: expected_time_seconds = 3600 * max_tokens / 128000
        """
        return math.floor(timeout_seconds * 128000 / 3600)
