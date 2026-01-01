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
from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.mistral.mistral_exceptions import MistralExtractResponseError
from pipelex.plugins.openai.openai_utils import make_image_url_obj
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

    def make_simple_messages(self, llm_job: LLMJob) -> list[Messages]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        messages: list[Messages] = []
        user_content: list[ContentChunk] = []
        if user_text := llm_job.llm_prompt.user_text:
            user_content.append(TextChunk(text=user_text))
        if user_images := llm_job.llm_prompt.user_images:
            user_content.extend(self.make_mistral_image_url(user_image) for user_image in user_images)
        if user_content:
            messages.append(UserMessage(content=user_content))

        if system_text := llm_job.llm_prompt.system_text:
            messages.append(SystemMessage(content=system_text))

        return messages

    def make_mistral_image_url(self, prompt_image: PromptImage) -> ImageURLChunk:
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

    async def make_simple_messages_openai_typed(
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

        if user_images := llm_prompt.user_images:
            for prompt_image in user_images:
                image_url_obj = await make_image_url_obj(prompt_image=prompt_image, detail=llm_job.job_params.image_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    def make_nb_tokens_by_category(self, usage: UsageInfo) -> NbTokensByCategoryDict:
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
        if not mistral_ocr_image_obj.image_base64:
            msg = "Mistral OCR image object does not have an image base64"
            raise MistralExtractResponseError(msg)
        width: int | None = None
        height: int | None = None
        if mistral_ocr_image_obj.top_left_x is not None and mistral_ocr_image_obj.bottom_right_x is not None:
            width = mistral_ocr_image_obj.bottom_right_x - mistral_ocr_image_obj.top_left_x
        if mistral_ocr_image_obj.top_left_y is not None and mistral_ocr_image_obj.bottom_right_y is not None:
            height = mistral_ocr_image_obj.bottom_right_y - mistral_ocr_image_obj.top_left_y
        size: ImageSize | None = None
        if width is not None and height is not None:
            size = ImageSize(width=width, height=height)
        bounding_box: BoundingBox | None
        if (
            mistral_ocr_image_obj.top_left_x is not None
            and mistral_ocr_image_obj.top_left_y is not None
            and mistral_ocr_image_obj.bottom_right_x is not None
            and mistral_ocr_image_obj.bottom_right_y is not None
        ):
            bounding_box = BoundingBox.make_from_two_corners(
                top_left_x=mistral_ocr_image_obj.top_left_x,
                top_left_y=mistral_ocr_image_obj.top_left_y,
                bottom_right_x=mistral_ocr_image_obj.bottom_right_x,
                bottom_right_y=mistral_ocr_image_obj.bottom_right_y,
            )
        else:
            bounding_box = None

        return ExtractedImageFromPage(
            size=size,
            base64_str=mistral_ocr_image_obj.image_base64,
            mime_type="image/jpeg",  # Mistral OCR returns JPEG images
            bounding_box=bounding_box,
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
