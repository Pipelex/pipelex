import asyncio
from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic, AsyncAnthropicBedrock
from anthropic.types import Usage
from anthropic.types.message_param import MessageParam
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImagePath,
    PromptImageTypedBase64,
    PromptImageTypedUrlOrBase64,
    PromptImageUrl,
)
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.base_64_utils import load_binary_as_base64_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from anthropic.types.image_block_param import ImageBlockParam
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

    @classmethod
    async def make_user_message(
        cls,
        llm_job: LLMJob,
    ) -> MessageParam:
        message: MessageParam
        content: list[TextBlockParam | ImageBlockParam] = []

        if llm_job.llm_prompt.user_text:
            text_block_param: TextBlockParam = {
                "type": "text",
                "text": llm_job.llm_prompt.user_text,
            }
            content.append(text_block_param)
        if llm_job.llm_prompt.user_images:
            tasks_to_prep_images = [cls._prep_image_for_anthropic(prompt_image) for prompt_image in llm_job.llm_prompt.user_images]
            prepped_user_images = await asyncio.gather(*tasks_to_prep_images)
            # images_block_params: List[ImageBlockParam] = []
            for prepped_image in prepped_user_images:
                image_block_param: ImageBlockParam
                if isinstance(prepped_image, PromptImageTypedBase64):
                    mime = prepped_image.file_type.mime
                    image_block_param = {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,  # type: ignore[typeddict-item]
                            "data": prepped_image.base_64.decode("utf-8"),
                        },  # pyright: ignore[reportAssignmentType]
                    }
                elif isinstance(prepped_image, str):  # pyright: ignore[reportUnnecessaryIsInstance]
                    url = prepped_image
                    image_block_param = {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url,
                        },
                    }
                else:
                    msg = f"Unsupported PromptImageTypedBytesOrUrl type: '{type(prepped_image).__name__}'"
                    raise AnthropicFactoryError(msg)
                content.append(image_block_param)

        message = {
            "role": "user",
            "content": content,
        }

        return message

    # This creates a MessageParam disguised as a ChatCompletionMessageParam to please instructor type checking
    @staticmethod
    def openai_typed_user_message(
        user_content_txt: str,
        prepped_user_images: list[PromptImageTypedUrlOrBase64] | None = None,
    ) -> ChatCompletionMessageParam:
        text_block_param: TextBlockParam = {"type": "text", "text": user_content_txt}
        message: MessageParam
        if prepped_user_images is not None:
            log.debug(prepped_user_images)
            images_block_params: list[ImageBlockParam] = []
            for prepped_image in prepped_user_images:
                image_block_param_in_loop: ImageBlockParam
                if isinstance(prepped_image, PromptImageTypedBase64):
                    mime = prepped_image.file_type.mime
                    image_block_param_in_loop = {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,  # type: ignore[typeddict-item]
                            "data": prepped_image.base_64.decode("utf-8"),
                        },  # pyright: ignore[reportAssignmentType]
                    }
                elif isinstance(prepped_image, str):  # pyright: ignore[reportUnnecessaryIsInstance]
                    url = prepped_image
                    image_block_param_in_loop = {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url,
                        },
                    }
                else:
                    msg = f"Unsupported PromptImageTypedBytesOrUrl type: '{type(prepped_image).__name__}'"
                    raise AnthropicFactoryError(msg)
                images_block_params.append(image_block_param_in_loop)

            content: list[TextBlockParam | ImageBlockParam] = [*images_block_params, text_block_param]
            message = {
                "role": "user",
                "content": content,
            }

        else:
            message = {
                "role": "user",
                "content": [text_block_param],
            }

        return message  # type: ignore[return-value, valid-type] # pyright: ignore[reportReturnType]

    @classmethod
    async def _prep_image_for_anthropic(
        cls,
        prompt_image: PromptImage,
    ) -> PromptImageTypedUrlOrBase64:
        typed_bytes_or_url: PromptImageTypedUrlOrBase64
        if isinstance(prompt_image, PromptImageBase64):
            typed_bytes_or_url = prompt_image.make_prompt_image_typed_base64()
        elif isinstance(prompt_image, PromptImageUrl):
            image_bytes = await PromptImageFactory.make_promptimagebase64_from_url_async(prompt_image)
            file_type = detect_file_type_from_base64(image_bytes.base_64)
            typed_bytes_or_url = PromptImageTypedBase64(base_64=image_bytes.base_64, file_type=file_type)
        elif isinstance(prompt_image, PromptImagePath):
            b64 = await load_binary_as_base64_async(prompt_image.file_path)
            typed_bytes_or_url = PromptImageTypedBase64(base_64=b64, file_type=prompt_image.get_file_type())
        else:
            msg = f"Unsupported PromptImage type: '{type(prompt_image).__name__}'"
            raise AnthropicFactoryError(msg)
        return typed_bytes_or_url

    @classmethod
    async def make_simple_messages(
        cls,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        #### System message ####
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))

        prepped_user_images: list[PromptImageTypedUrlOrBase64] | None
        if llm_prompt.user_images:
            tasks_to_prep_images = [cls._prep_image_for_anthropic(prompt_image) for prompt_image in llm_prompt.user_images]
            prepped_user_images = await asyncio.gather(*tasks_to_prep_images)
        else:
            prepped_user_images = None

        #### Concatenation ####
        messages.append(
            AnthropicFactory.openai_typed_user_message(
                user_content_txt=llm_prompt.user_text if llm_prompt.user_text else "",
                prepped_user_images=prepped_user_images,
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
