import os

import aiofiles
import mistralai
from mistralai import Mistral
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
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64, detect_file_type_from_path


class MistralFactory:
    #########################################################
    # Client
    #########################################################

    @classmethod
    def make_mistral_client(
        cls,
        backend: InferenceBackend,
    ) -> Mistral:
        return Mistral(api_key=backend.api_key)

    #########################################################
    # Message
    #########################################################

    @classmethod
    def make_simple_messages(cls, llm_job: LLMJob) -> list[Messages]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        messages: list[Messages] = []
        user_content: list[ContentChunk] = []
        if user_text := llm_job.llm_prompt.user_text:
            user_content.append(TextChunk(text=user_text))
        if user_images := llm_job.llm_prompt.user_images:
            user_content.extend(cls.make_mistral_image_url(user_image) for user_image in user_images)
        if user_content:
            messages.append(UserMessage(content=user_content))

        if system_text := llm_job.llm_prompt.system_text:
            messages.append(SystemMessage(content=system_text))

        return messages

    @classmethod
    def make_mistral_image_url(cls, prompt_image: PromptImage) -> ImageURLChunk:
        if isinstance(prompt_image, PromptImageUrl):
            return ImageURLChunk(image_url=prompt_image.url)
        if isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(prompt_image.file_path).decode("utf-8")
            file_type = detect_file_type_from_path(prompt_image.file_path)
            return ImageURLChunk(image_url=f"data:{file_type.mime};base64,{image_bytes}")
        if isinstance(prompt_image, PromptImageBase64):
            image_bytes = prompt_image.base_64.decode("utf-8")
            file_type = detect_file_type_from_base64(prompt_image.base_64)
            return ImageURLChunk(image_url=f"data:{file_type.mime};base64,{image_bytes}")
        msg = f"prompt_image of type {type(prompt_image)} is not supported"
        raise PromptImageFormatError(msg)

    @classmethod
    def make_simple_messages_openai_typed(
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
    async def make_extract_output_from_mistral_response(
        cls,
        mistral_extract_response: mistralai.OCRResponse,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        pages: dict[int, Page] = {}
        for response_page in mistral_extract_response.pages:
            page = Page(
                text=response_page.markdown,
                extracted_images=[],
            )
            if should_include_images:
                for mistral_ocr_image_obj in response_page.images:
                    extracted_image = cls.make_extracted_image_from_page_from_mistral_ocr_image_obj(mistral_ocr_image_obj)
                    page.extracted_images.append(extracted_image)
            pages[response_page.index] = page

        return ExtractOutput(
            pages=pages,
        )

    @classmethod
    def make_extracted_image_from_page_from_mistral_ocr_image_obj(
        cls,
        mistral_ocr_image_obj: mistralai.OCRImageObject,
    ) -> ExtractedImageFromPage:
        return ExtractedImageFromPage(
            image_id=mistral_ocr_image_obj.id,
            top_left_x=mistral_ocr_image_obj.top_left_x,
            top_left_y=mistral_ocr_image_obj.top_left_y,
            bottom_right_x=mistral_ocr_image_obj.bottom_right_x,
            bottom_right_y=mistral_ocr_image_obj.bottom_right_y,
            base_64=mistral_ocr_image_obj.image_base64 if mistral_ocr_image_obj.image_base64 else None,
        )

    #########################################################
    # Utils
    #########################################################
    @classmethod
    async def upload_file_to_mistral_for_ocr(
        cls,
        mistral_client: Mistral,
        file_path: str,
    ) -> str:
        """Upload a local file to Mistral.

        Args:
            file_path: Path to the local file to upload
            mistral_client: Mistral client

        Returns:
            ID of the uploaded file

        """
        async with aiofiles.open(file_path, "rb") as file:  # pyright: ignore[reportUnknownMemberType]
            file_content = await file.read()

        uploaded_file = await mistral_client.files.upload_async(
            file={"file_name": os.path.basename(file_path), "content": file_content},
            purpose="ocr",
        )
        return uploaded_file.id
