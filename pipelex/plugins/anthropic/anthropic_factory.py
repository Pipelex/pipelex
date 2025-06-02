import asyncio
from typing import List, Optional, Union

from anthropic import AsyncAnthropic, AsyncAnthropicBedrock
from anthropic.types import Usage
from anthropic.types.image_block_param import ImageBlockParam
from anthropic.types.message_param import MessageParam
from anthropic.types.text_block_param import TextBlockParam
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBytes,
    PromptImagePath,
    PromptImageTypedBytes,
    PromptImageTypedBytesOrUrl,
    PromptImageUrl,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.hub import get_secrets_provider
from pipelex.tools.misc.base_64_utils import (
    load_binary_as_base64_async,
)


class AnthropicFactoryError(CogtError):
    pass


class AnthropicFactory:
    @staticmethod
    def make_anthropic_client(
        llm_platform: LLMPlatform,
    ) -> Union[AsyncAnthropic, AsyncAnthropicBedrock]:
        # TODO: also support Anthropic with VertexAI
        match llm_platform:
            case LLMPlatform.ANTHROPIC:
                anthropic_config = get_config().plugins.anthropic_config
                api_key = anthropic_config.get_api_key(secrets_provider=get_secrets_provider())
                return AsyncAnthropic(api_key=api_key)
            case LLMPlatform.BEDROCK_ANTHROPIC:
                aws_config = get_config().pipelex.aws_config
                aws_access_key_id, aws_secret_access_key, aws_region = aws_config.get_aws_access_keys()
                return AsyncAnthropicBedrock(
                    aws_secret_key=aws_secret_access_key,
                    aws_access_key=aws_access_key_id,
                    aws_region=aws_region,
                )
            case _:
                raise AnthropicFactoryError(f"Unsupported LLM platform for Anthropic sdk: '{llm_platform}'")

    @classmethod
    async def make_user_message(
        cls,
        llm_job: LLMJob,
    ) -> MessageParam:
        message: MessageParam
        content: List[Union[TextBlockParam, ImageBlockParam]] = []

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
                if isinstance(prepped_image, PromptImageTypedBytes):
                    mime = prepped_image.file_type.mime
                    image_block_param = {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,  # type: ignore
                            "data": prepped_image.image_bytes.decode("utf-8"),
                        },  # type: ignore
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
                    raise AnthropicFactoryError(f"Unsupported PromptImageTypedBytesOrUrl type: '{type(prepped_image).__name__}'")
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
        prepped_user_images: Optional[List[PromptImageTypedBytesOrUrl]] = None,
    ) -> ChatCompletionMessageParam:
        text_block_param: TextBlockParam = {"type": "text", "text": user_content_txt}
        message: MessageParam
        if prepped_user_images is not None:
            log.debug(prepped_user_images)
            images_block_params: List[ImageBlockParam] = []
            for prepped_image in prepped_user_images:
                image_block_param_in_loop: ImageBlockParam
                if isinstance(prepped_image, PromptImageTypedBytes):
                    mime = prepped_image.file_type.mime
                    image_block_param_in_loop = {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,  # type: ignore
                            "data": prepped_image.image_bytes.decode("utf-8"),
                        },  # type: ignore
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
                    raise AnthropicFactoryError(f"Unsupported PromptImageTypedBytesOrUrl type: '{type(prepped_image).__name__}'")
                log.debug(image_block_param_in_loop)
                images_block_params.append(image_block_param_in_loop)

            content: List[Union[TextBlockParam, ImageBlockParam]] = images_block_params + [text_block_param]
            message = {
                "role": "user",
                "content": content,
            }

        else:
            message = {
                "role": "user",
                "content": [text_block_param],
            }

        return message  # type: ignore

    @classmethod
    async def _prep_image_for_anthropic(
        cls,
        prompt_image: PromptImage,
    ) -> PromptImageTypedBytesOrUrl:
        typed_bytes_or_url: PromptImageTypedBytesOrUrl
        if isinstance(prompt_image, PromptImageBytes):
            typed_bytes_or_url = prompt_image.make_prompt_image_typed_bytes()
        elif isinstance(prompt_image, PromptImageUrl):
            typed_bytes_or_url = prompt_image.url
        elif isinstance(prompt_image, PromptImagePath):
            b64 = await load_binary_as_base64_async(prompt_image.file_path)
            typed_bytes_or_url = PromptImageTypedBytes(image_bytes=b64, file_type=prompt_image.get_file_type())
        else:
            raise AnthropicFactoryError(f"Unsupported PromptImage type: '{type(prompt_image).__name__}'")
        return typed_bytes_or_url

    @classmethod
    async def make_simple_messages(
        cls,
        llm_job: LLMJob,
    ) -> List[ChatCompletionMessageParam]:
        """
        Makes a list of messages with a system message (if provided) and followed by a user message.
        """
        llm_prompt = llm_job.llm_prompt
        messages: List[ChatCompletionMessageParam] = []
        #### System message ####
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))

        prepped_user_images: Optional[List[PromptImageTypedBytesOrUrl]]
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
            )
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
