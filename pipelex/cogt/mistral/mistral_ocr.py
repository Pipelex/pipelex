# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import asyncio
import os
from typing import Dict, List, Optional

import aiofiles
import shortuuid

# from mistralai import OCRImageObject as MistralOCRImageObject
# from mistralai import OCRResponse as MistralOCRResponse
from mistralai import OCRImageObject, OCRResponse
from PIL import Image
from typing_extensions import override

from pipelex.cogt.mistral.mistral_factory import MistralFactory
from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_extraction_models import OcrExtractedImage, OcrOutput, Page
from pipelex.config import get_config
from pipelex.tools.misc.base_64 import (
    load_binary_as_base64,
)
from pipelex.tools.pdf.pdf_render import render_pdf_pages_to_images
from pipelex.tools.utils.path_utils import clarify_path_or_url, ensure_path


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
    async def make_ocr_output_from_image(
        self,
        image_uri: str,
        should_caption_image: bool = False,
    ) -> OcrOutput:
        if should_caption_image:
            raise NotImplementedError("Captioning is not implemented for Mistral OCR.")
        image_path, image_url = clarify_path_or_url(path_or_url=image_uri)
        if image_url:
            return await self.extract_from_image_url(
                image_url=image_url,
            )
        else:  # image_path must be provided based on validation
            assert image_path is not None  # Type narrowing for mypy
            return await self.extract_from_image_file(
                image_path=image_path,
            )

    @override
    async def make_ocr_output_from_pdf(
        self,
        pdf_uri: str,
        should_caption_images: bool,
        should_add_screenshots: bool,
    ) -> OcrOutput:
        if should_caption_images:
            raise NotImplementedError("Captioning is not implemented for Mistral OCR.")
        pdf_path, pdf_url = clarify_path_or_url(path_or_url=pdf_uri)  # pyright: ignore
        ocr_output: OcrOutput
        if pdf_url:
            ocr_output = await self.extract_from_pdf_url(
                pdf_url=pdf_url,
            )
        else:  # pdf_path must be provided based on validation
            assert pdf_path is not None  # Type narrowing for mypy
            ocr_output = await self.extract_from_pdf_file(
                pdf_path=pdf_path,
            )
        if should_add_screenshots:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_uri=pdf_uri,
                ocr_output=ocr_output,
            )
        return ocr_output

    async def extract_from_image_url(
        self,
        image_url: str,
    ) -> OcrOutput:
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
        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

    async def extract_from_image_file(
        self,
        image_path: str,
    ) -> OcrOutput:
        """
        Process an image from a local file by encoding it to base64.

        Args:
            image_path: Path to the local image file
            caption_image: Whether to generate captions for the image

        Returns:
            OCR response containing extracted text and images
        """
        base64_image = load_binary_as_base64(path=image_path).decode("utf-8")

        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_model_name,
            document={"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"},
        )
        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        should_include_images: bool = False,
    ) -> OcrOutput:
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
            include_image_base64=should_include_images,
        )

        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        should_include_images: bool = False,
    ) -> OcrOutput:
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
            include_image_base64=should_include_images,
        )
        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

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

    async def add_page_screenshots_to_ocr_output(
        self,
        pdf_uri: str,
        ocr_output: OcrOutput,
    ) -> OcrOutput:
        screenshot_uris: List[str] = []
        pdf_path, pdf_url = clarify_path_or_url(pdf_uri)
        # TODO: use centralized / possibly online storage instead of local file system
        images = await render_pdf_pages_to_images(pdf_path=pdf_path, pdf_url=pdf_url, dpi=300)

        temp_directory_name = shortuuid.uuid()
        temp_directory_path = f"temp/{temp_directory_name}"
        ensure_path(temp_directory_path)

        # Save images to the folder and return their paths
        screenshot_uris = []
        for image_index, image in enumerate(images):
            image_path = f"{temp_directory_path}/page_{image_index}.png"
            image.save(image_path)
            screenshot_uris.append(image_path)
        for page_index, page in enumerate(ocr_output.pages.values()):
            screenshot_uri = screenshot_uris[page_index]
            page.screenshot = OcrExtractedImage(uri=screenshot_uri)
        return ocr_output
