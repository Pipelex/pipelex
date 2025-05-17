# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import asyncio
import os
from typing import Dict, List, Optional

import aiofiles
from mistralai import OCRImageObject, OCRResponse
from typing_extensions import override

from pipelex.cogt.mistral.mistral_factory import MistralFactory
from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract, OCRExtractedImage, OCROutput, Page
from pipelex.cogt.ocr.ocr_utils import pdf_to_saved_page_screenshot_paths
from pipelex.config import get_config
from pipelex.tools.utils.image_utils import (
    load_image_as_base64_from_path,
)
from pipelex.tools.utils.path_utils import clarify_path_or_url


class MistralOCRError(ValueError):
    pass


class MistralOCREngine(OCREngineAbstract):
    """
    A wrapper class for Mistral OCR functionality.
    Provides methods to process documents and images.
    """

    def __init__(self):
        """Initialize the MistralOCR class with a Mistral client."""
        self.mistral_client = MistralFactory.make_mistral_client()
        self.ocr_model_name = get_config().cogt.ocr_config.mistral_ocr_config.ocr_model_name

    @override
    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        caption_image: bool = False,
        get_screenshot: bool = False,
        include_image_base64: bool = False,
    ) -> OCROutput:
        """
        Process a PDF from its URL.

        Args:
            url: URL of the PDF to process
            caption_image: Whether to generate captions for extracted images
            include_image_base64: Whether to include base64-encoded images in the response

        Returns:
            OCR response containing extracted text and images
        """
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_model_name,
            document={
                "type": "document_url",
                "document_url": pdf_url,
            },
            include_image_base64=include_image_base64,
        )

        ocr_output = await self.ocr_result_from_response(
            ocr_response=ocr_response,
            caption_image=caption_image,
        )

        if get_screenshot:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_url=pdf_url,
                image_url=None,
                ocr_output=ocr_output,
            )
        return ocr_output

    @override
    async def extract_from_image_url(
        self,
        image_url: str,
        caption_image: bool = False,
        get_screenshot: bool = False,
    ) -> OCROutput:
        """
        Process an image from its URL.

        Args:
            image_url: URL of the image to process
            caption_image: Whether to generate captions for the image

        Returns:
            OCR response containing extracted text and images
        """
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_model_name,
            document={
                "type": "image_url",
                "image_url": image_url,
            },
        )
        ocr_output = await self.ocr_result_from_response(
            ocr_response=ocr_response,
            caption_image=caption_image,
        )
        if get_screenshot:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_url=None,
                image_url=image_url,
                ocr_output=ocr_output,
            )
        return ocr_output

    @override
    async def extract_from_image_file(
        self,
        image_path: str,
        caption_image: bool = False,
        get_screenshot: bool = False,
    ) -> OCROutput:
        """
        Process an image from a local file by encoding it to base64.

        Args:
            image_path: Path to the local image file
            caption_image: Whether to generate captions for the image

        Returns:
            OCR response containing extracted text and images
        """
        base64_image = load_image_as_base64_from_path(path=image_path).decode("utf-8")

        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_model_name,
            document={"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"},
        )
        ocr_output = await self.ocr_result_from_response(
            ocr_response=ocr_response,
            caption_image=caption_image,
        )
        if get_screenshot:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_url=None,
                image_url=image_path,
                ocr_output=ocr_output,
            )
        return ocr_output

    @override
    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        caption_image: bool = False,
        get_screenshot: bool = False,
    ) -> OCROutput:
        """
        Upload a PDF file and process it with OCR.

        Args:
            pdf_path: Path to the local PDF file
            caption_image: Whether to generate captions for extracted images

        Returns:
            OCR response containing extracted text and images
        """
        # Upload the file
        uploaded_file_id = await self.upload_local_pdf(pdf_path)

        # Get signed URL
        signed_url = await self.mistral_client.files.get_signed_url_async(
            file_id=uploaded_file_id,
        )

        # Process the document
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_model_name,
            document={
                "type": "document_url",
                "document_url": signed_url.url,
            },
        )
        ocr_output = await self.ocr_result_from_response(
            ocr_response=ocr_response,
            caption_image=caption_image,
        )
        if get_screenshot:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_url=pdf_path,
                image_url=None,
                ocr_output=ocr_output,
            )
        return ocr_output

    @override
    async def caption_image(
        self,
        image_uri: str,
    ) -> str:
        raise NotImplementedError("Captioning is not implemented for Mistral OCR.")

    async def upload_local_pdf(
        self,
        pdf_path: str,
    ) -> str:
        """
        Upload a local file to Mistral.

        Args:
            pdf_path: Path to the local file to upload

        Returns:
            ID of the uploaded file
        """
        async with aiofiles.open(pdf_path, "rb") as file:  # type: ignore[reportUnknownMemberType]
            file_content = await file.read()

        uploaded_file = await self.mistral_client.files.upload_async(
            file={"file_name": os.path.basename(pdf_path), "content": file_content},
            purpose="ocr",
        )
        return uploaded_file.id

    # TODO: use hash instead of id
    async def ocr_extracted_image_from_mistral_ocr_image_object(
        self,
        ocr_image_data: OCRImageObject,
        caption_image: bool = False,
    ) -> OCRExtractedImage:
        image_uri = ocr_image_data.id
        image = OCRExtractedImage(uri=image_uri)
        if caption_image:
            image_caption = await self.caption_image(image_uri=image_uri)
            image.caption = image_caption
        return image

    async def ocr_extracted_images_from_ocr_response(
        self,
        ocr_response: OCRResponse,
        caption_image: bool,
    ) -> List[OCRExtractedImage]:
        """
        Extract images from an OCR response and turn them into OCRExtractedImage objects.

        Args:
            ocr_response: OCR response to extract images from
            caption_image: Whether to generate captions for the images

        Returns:
            List of OCRExtractedImage objects
        """
        # Collect all image tasks using list comprehension
        tasks = [
            self.ocr_extracted_image_from_mistral_ocr_image_object(image, caption_image=caption_image)
            for page in ocr_response.pages
            for image in page.images
        ]

        # Process all images concurrently
        images = await asyncio.gather(*tasks)
        return images

    async def ocr_result_from_response(
        self,
        ocr_response: OCRResponse,
        caption_image: bool,
    ) -> OCROutput:
        """
        Extract text and images from an OCR response and turn them into an OCROutput object.

        Args:
            ocr_response: OCR response to extract text and images from
            caption_image: Whether to generate captions for the images

        Returns:
            OCROutput object containing extracted text and images
        """
        pages: Dict[int, Page] = {}
        for ocr_response_page in ocr_response.pages:
            pages[ocr_response_page.index] = Page(
                text=ocr_response_page.markdown,
                images=[],
            )
            for ocr_response_image in ocr_response_page.images:
                image = await self.ocr_extracted_image_from_mistral_ocr_image_object(
                    ocr_image_data=ocr_response_image,
                    caption_image=caption_image,
                )
                pages[ocr_response_page.index].images.append(image)

        return OCROutput(
            pages=pages,
        )

    @override
    async def add_page_screenshots_to_ocr_output(
        self,
        pdf_url: Optional[str],
        image_url: Optional[str],
        ocr_output: OCROutput,
    ) -> OCROutput:
        if image_url:
            screenshot_paths = [image_url]
        elif pdf_url:
            pdf_path, pdf_url = clarify_path_or_url(pdf_url)
            # TODO: use centralized / possibly online storage instead of local file system
            screenshot_paths = await pdf_to_saved_page_screenshot_paths(pdf_path=pdf_path, pdf_url=pdf_url)
        else:
            raise MistralOCRError("Either image_url or pdf_url must be provided")
        for page_index, page in enumerate(ocr_output.pages.values()):
            screenshot_path = screenshot_paths[page_index]
            page.screenshot = OCRExtractedImage(uri=screenshot_path)
        return ocr_output
