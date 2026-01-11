import asyncio
import base64
import os

import aiofiles
import mistralai
from mistralai import Mistral
from mistralai.models import (
    ContentChunk,
    DocumentURLChunk,
    DocumentURLChunkTypedDict,
    ImageURLChunk,
    ImageURLChunkTypedDict,
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
from openai.types.chat.chat_completion_content_part_image_param import ImageURL as OpenAIImageURL

from pipelex import log
from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents
from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.file.file_preparation_utils import prepare_file_from_uri
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images, prepare_prompt_image
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.mistral.mistral_exceptions import MistralExtractResponseError
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath


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

    async def make_simple_messages(self, llm_job: LLMJob) -> list[Messages]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        messages: list[Messages] = []
        user_content: list[ContentChunk] = []
        if user_text := llm_job.llm_prompt.user_text:
            user_content.append(TextChunk(text=user_text))
        if user_images := llm_job.llm_prompt.user_images:
            image_chunks = await asyncio.gather(*(self.make_mistral_image_url(prompt_image=img) for img in user_images))
            user_content.extend(image_chunks)
        if user_documents := llm_job.llm_prompt.user_documents:
            document_chunks = await asyncio.gather(*(self.make_mistral_document_url(prompt_document=doc) for doc in user_documents))
            user_content.extend(document_chunks)
        if user_content:
            messages.append(UserMessage(content=user_content))

        if system_text := llm_job.llm_prompt.system_text:
            messages.append(SystemMessage(content=system_text))

        return messages

    async def make_mistral_image_url(self, prompt_image: PromptImage) -> ImageURLChunk:
        """Convert a PromptImage to a Mistral ImageURLChunk.

        Uses the unified prepare_prompt_image() which supports all URI types
        including pipelex-storage://.
        """
        # Mistral accepts HTTP URLs directly, so we enable them
        prepared = await prepare_prompt_image(prompt_image=prompt_image, is_http_url_enabled=True)

        image_url: str
        match prepared:
            case PreparedFileBase64():
                image_url = prepared.as_data_url()
            case PreparedFileHttpUrl():
                image_url = prepared.url
            case PreparedFileLocalPath():
                msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                raise TypeError(msg)

        return ImageURLChunk(image_url=image_url)

    async def make_mistral_document_url(self, prompt_document: PromptDocument) -> DocumentURLChunk:
        """Convert a PromptDocument to a Mistral DocumentURLChunk.

        Uses the unified prep_prompt_documents() which supports all URI types
        including pipelex-storage://.
        """
        # Mistral accepts HTTP URLs directly, so we enable them
        prepped_documents = await prep_prompt_documents(prompt_documents=[prompt_document], is_http_url_enabled=True)
        prepped = prepped_documents[0]

        document_url: str
        match prepped:
            case PreparedFileBase64():
                document_url = prepped.as_data_url()
            case PreparedFileHttpUrl():
                document_url = prepped.url
            case PreparedFileLocalPath():
                msg = "PreparedFileLocalPath is not supported for documents - should be converted to base64"
                raise TypeError(msg)

        return DocumentURLChunk(document_url=document_url)

    async def make_simple_messages_openai_typed(
        self,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message.

        Uses the unified prep_prompt_images() which supports all URI types
        including pipelex-storage://.
        """
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
            detail = llm_job.job_params.image_detail or PromptImageDetail.AUTO
            # Mistral accepts HTTP URLs directly
            prepared_images = await prep_prompt_images(prompt_images=user_images, is_http_url_enabled=True)
            for prepared in prepared_images:
                url: str
                match prepared:
                    case PreparedFileBase64():
                        url = prepared.as_data_url()
                    case PreparedFileHttpUrl():
                        url = prepared.url
                    case PreparedFileLocalPath():
                        msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                        raise TypeError(msg)

                image_url_obj = OpenAIImageURL(url=url, detail=detail.as_openai_detail)
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
    ) -> ExtractOutput:
        """Convert Mistral OCR response to ExtractOutput.

        Images are included if present in the response (controlled by image_limit in the API call).
        """
        pages: dict[int, Page] = {}
        for response_page in mistral_extract_response.pages:
            extracted_images: list[ExtractedImageFromPage] = []
            for mistral_ocr_image_obj in response_page.images:
                extracted_image = cls.make_extracted_image_from_page_from_mistral_ocr_image_obj(mistral_ocr_image_obj)
                extracted_images.append(extracted_image)
            page = Page(
                text=response_page.markdown,
                extracted_images=extracted_images,
            )
            pages[response_page.index] = page

        return ExtractOutput(
            pages=pages,
        )

    @classmethod
    def _clean_mistral_image_base64(cls, base64_str: str) -> str:
        """Clean Mistral's base64 image data by removing prepended metadata bytes.

        Mistral OCR sometimes prepends metadata bytes before the actual image data.
        This method scans for the image magic number and removes everything before it.

        Args:
            base64_str: The base64-encoded image string from Mistral

        Returns:
            Cleaned base64 string with metadata removed if it was present
        """
        log.debug("=== Cleaning Mistral image base64 ===")
        try:
            decoded_bytes = base64.b64decode(base64_str)
            log.debug(f"Decoded image length: {len(decoded_bytes)} bytes")
            log.debug(f"First 24 bytes (hex): {decoded_bytes[:24].hex()}")

            # Image file magic numbers
            jpeg_magic = b"\xff\xd8"  # JPEG SOI (Start of Image) - FF D8
            png_magic = b"\x89PNG"  # PNG signature

            # Check if the data already starts with a valid image magic number
            if decoded_bytes[:2] == jpeg_magic:
                log.debug("Image already starts with JPEG magic (FF D8), no cleaning needed")
                return base64_str
            if decoded_bytes[:4] == png_magic:
                log.debug("Image already starts with PNG magic, no cleaning needed")
                return base64_str

            # Scan for JPEG magic in the first 32 bytes
            jpeg_pos = decoded_bytes[:32].find(jpeg_magic)
            if jpeg_pos > 0:
                log.debug(f"Found JPEG magic (FF D8) at byte position {jpeg_pos}")
                cleaned_bytes = decoded_bytes[jpeg_pos:]
                log.debug(f"Cleaned image length: {len(cleaned_bytes)} bytes")
                log.debug(f"Cleaned first 20 bytes (hex): {cleaned_bytes[:20].hex()}")
                return base64.b64encode(cleaned_bytes).decode("ascii")

            # Scan for PNG magic in the first 32 bytes
            png_pos = decoded_bytes[:32].find(png_magic)
            if png_pos > 0:
                log.debug(f"Found PNG magic at byte position {png_pos}")
                cleaned_bytes = decoded_bytes[png_pos:]
                log.debug(f"Cleaned image length: {len(cleaned_bytes)} bytes")
                log.debug(f"Cleaned first 20 bytes (hex): {cleaned_bytes[:20].hex()}")
                return base64.b64encode(cleaned_bytes).decode("ascii")

            log.debug("No image magic number found in first 32 bytes, returning original")
            return base64_str
        except Exception as exc:
            # If anything goes wrong, return the original base64 string
            log.debug(f"Error cleaning base64: {exc}")
            return base64_str

    @classmethod
    def make_extracted_image_from_page_from_mistral_ocr_image_obj(
        cls,
        mistral_ocr_image_obj: mistralai.OCRImageObject,
    ) -> ExtractedImageFromPage:
        if not mistral_ocr_image_obj.image_base64:
            msg = "Mistral OCR image object does not have an image base64"
            raise MistralExtractResponseError(msg)

        # Clean the base64 data to remove any prepended metadata bytes
        cleaned_base64 = cls._clean_mistral_image_base64(mistral_ocr_image_obj.image_base64)

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
            base64_str=cleaned_base64,
            mime_type="image/jpeg",  # Mistral OCR returns JPEG images
            bounding_box=bounding_box,
        )

    #########################################################
    # Document preparation for OCR
    #########################################################

    @classmethod
    async def make_mistral_image_url_chunk_from_uri(
        cls,
        uri: str,
    ) -> ImageURLChunkTypedDict:
        """Create a Mistral image_url document from a URI.

        Resolves the URI and converts it to a format suitable for Mistral's OCR API.
        Supports HTTP URLs (kept as-is) and local paths (converted to base64 data URLs).

        Args:
            uri: The URI string to resolve (HTTP URL, local path, etc.)

        Returns:
            An ImageURLChunkTypedDict suitable for Mistral OCR API

        Example:
            >>> doc = await make_mistral_image_url_chunk_from_uri("https://example.com/image.png")
            >>> doc
            {"type": "image_url", "image_url": "https://example.com/image.png"}
        """
        prepared = await prepare_file_from_uri(uri=uri, keep_http_url=True, keep_local_path=False)

        image_url: str
        match prepared:
            case PreparedFileHttpUrl():
                image_url = prepared.url
            case PreparedFileBase64():
                image_url = prepared.as_data_url()
            case PreparedFileLocalPath():
                # This shouldn't happen since we use keep_local_path=False
                msg = f"Unexpected PreparedFileLocalPath for URI: {uri}"
                raise TypeError(msg)

        return ImageURLChunkTypedDict(
            type="image_url",
            image_url=image_url,
        )

    @classmethod
    async def make_mistral_document_url_chunk_from_uri(
        cls,
        mistral_client: Mistral,
        uri: str,
    ) -> DocumentURLChunkTypedDict:
        """Create a Mistral document_url document from a URI.

        Resolves the URI and converts it to a format suitable for Mistral's OCR API.
        For HTTP URLs: kept as-is
        For local paths: uploads to Mistral and gets a signed URL

        Args:
            mistral_client: Mistral client (required for local file uploads)
            uri: The URI string to resolve (HTTP URL, local path, etc.)

        Returns:
            A DocumentURLChunkTypedDict suitable for Mistral OCR API

        Raises:
            ValueError: If mistral_client is None and a local file needs to be uploaded

        Example:
            >>> doc = await make_mistral_document_url_chunk_from_uri("https://example.com/doc.pdf")
            >>> doc
            {"type": "document_url", "document_url": "https://example.com/doc.pdf"}
        """
        prepared = await prepare_file_from_uri(uri=uri, keep_http_url=True, keep_local_path=True)

        document_url: str
        match prepared:
            case PreparedFileHttpUrl():
                document_url = prepared.url
            case PreparedFileLocalPath():
                uploaded_file_id = await cls.upload_file_to_mistral_for_ocr(
                    mistral_client=mistral_client,
                    file_path=prepared.path,
                )
                signed_url_response = await mistral_client.files.get_signed_url_async(file_id=uploaded_file_id)
                document_url = signed_url_response.url
            case PreparedFileBase64():
                # For base64 or other types, we'd need to handle differently
                # For now, convert to base64 data URL
                prepared_as_base64 = await prepare_file_from_uri(uri=uri, keep_http_url=False, keep_local_path=False)
                if not isinstance(prepared_as_base64, PreparedFileBase64):
                    msg = f"Failed to convert URI to base64: {uri}"
                    raise TypeError(msg)
                document_url = prepared_as_base64.as_data_url()

        return DocumentURLChunkTypedDict(
            type="document_url",
            document_url=document_url,
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
