from typing import Dict, List

from mistralai import Mistral, OCRImageObject, OCRResponse
from mistralai.models import (
    ContentChunk,
    ImageURLChunk,
    Messages,
    SystemMessage,
    TextChunk,
    UsageInfo,
    UserMessage,
)
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from pipelex.cogt.exceptions import PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.cogt.ocr.ocr_output import ExtractedImageFromPage, OcrOutput, Page
from pipelex.config import get_config
from pipelex.hub import get_secrets_provider
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.tools.misc.base_64_utils import encode_to_base64, load_binary_as_base64


class MistralFactory:
    #########################################################
    # Client
    #########################################################

    @classmethod
    def make_mistral_client(cls) -> Mistral:
        return Mistral(
            api_key=get_config().plugins.mistral_config.api_key(secrets_provider=get_secrets_provider()),
        )

    #########################################################
    # Message
    #########################################################

    @classmethod
    def make_simple_messages(cls, llm_job: LLMJob) -> List[Messages]:
        """
        Makes a list of messages with a system message (if provided) and followed by a user message.
        """
        messages: List[Messages] = []
        user_content: List[ContentChunk] = []
        if user_text := llm_job.llm_prompt.user_text:
            user_content.append(TextChunk(text=user_text))
        if user_images := llm_job.llm_prompt.user_images:
            for user_image in user_images:
                user_content.append(cls.make_mistral_image_url(user_image))
        if user_content:
            messages.append(UserMessage(content=user_content))

        if system_text := llm_job.llm_prompt.system_text:
            messages.append(SystemMessage(content=system_text))

        return messages

    @classmethod
    def make_mistral_image_url(cls, prompt_image: PromptImage) -> ImageURLChunk:
        if isinstance(prompt_image, PromptImageUrl):
            return ImageURLChunk(image_url=prompt_image.url)
        elif isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(prompt_image.file_path).decode("utf-8")
            # TODO: use actual image type
            return ImageURLChunk(image_url=f"data:image/png;base64,{image_bytes}")
        elif isinstance(prompt_image, PromptImageBytes):
            image_bytes = encode_to_base64(prompt_image.b64_image_bytes).decode("utf-8")
            # TODO: use actual image type
            return ImageURLChunk(image_url=f"data:image/png;base64,{image_bytes}")
        else:
            raise PromptImageFormatError(f"prompt_image of type {type(prompt_image)} is not supported")

    @classmethod
    def make_simple_messages_openai_typed(
        cls,
        llm_job: LLMJob,
    ) -> List[ChatCompletionMessageParam]:
        """
        Makes a list of messages with a system message (if provided) and followed by a user message.
        """
        llm_prompt = llm_job.llm_prompt
        messages: List[ChatCompletionMessageParam] = []
        user_contents: List[ChatCompletionContentPartParam] = []
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))
        # TODO: confirm that we can prompt without user_contents, for instance if we have only images,
        # otherwise consider using a default user_content
        if user_prompt_text := llm_prompt.user_text:
            user_part_text = ChatCompletionContentPartTextParam(text=user_prompt_text, type="text")
            user_contents.append(user_part_text)

        if user_images := llm_prompt.user_images:
            for prompt_image in user_images:
                openai_image_url = OpenAIFactory.make_openai_image_url(prompt_image=prompt_image)
                image_param = ChatCompletionContentPartImageParam(image_url=openai_image_url, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @staticmethod
    def make_nb_tokens_by_category(usage: UsageInfo) -> NbTokensByCategoryDict:
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.prompt_tokens,
            TokenCategory.OUTPUT: usage.completion_tokens,
        }
        return nb_tokens_by_category

    @classmethod
    async def make_ocr_output_from_mistral_response(
        cls,
        mistral_ocr_response: OCRResponse,
        should_include_images: bool = False,
        # export_dir: Optional[str] = None,
    ) -> OcrOutput:
        pages: Dict[int, Page] = {}
        for ocr_response_page in mistral_ocr_response.pages:
            page = Page(
                text=ocr_response_page.markdown,
                extracted_images=[],
            )
            if should_include_images:
                for mistral_ocr_image_obj in ocr_response_page.images:
                    extracted_image = cls.make_extracted_image_from_page_from_mistral_ocr_image_obj(mistral_ocr_image_obj)
                    page.extracted_images.append(extracted_image)
            pages[ocr_response_page.index] = page

        return OcrOutput(
            pages=pages,
        )

    @classmethod
    def make_extracted_image_from_page_from_mistral_ocr_image_obj(
        cls,
        mistral_ocr_image_obj: OCRImageObject,
    ) -> ExtractedImageFromPage:
        extracted_image = ExtractedImageFromPage(
            image_id=mistral_ocr_image_obj.id,
            top_left_x=mistral_ocr_image_obj.top_left_x,
            top_left_y=mistral_ocr_image_obj.top_left_y,
            bottom_right_x=mistral_ocr_image_obj.bottom_right_x,
            bottom_right_y=mistral_ocr_image_obj.bottom_right_y,
            base_64=mistral_ocr_image_obj.image_base64 if mistral_ocr_image_obj.image_base64 else None,
        )
        return extracted_image
