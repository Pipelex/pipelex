# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import os

import aiofiles
from mistralai import OCRResponse
from typing_extensions import override

from pipelex.cogt.mistral.mistral_factory import MistralFactory
from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract, OCROutput
from pipelex.config import get_config
from pipelex.tools.utils.image_utils import (
    load_image_as_base64_from_path,
)


class MistralOCREngine(OCREngineAbstract):
    """
    A wrapper class for Mistral OCR functionality.
    Provides methods to process documents and images.
    """

    def __init__(self):
        """Initialize the MistralOCR class with a Mistral client."""
        self.client = MistralFactory.make_mistral_client()
        self.model = get_config().cogt.ocr_config.mistral_ocr_config.ocr_model_name

    @override
    async def process_document_url(
        self,
        url: str,
        include_image_base64: bool = False,
    ) -> OCROutput:
        """
        Process a document from a URL.

        Args:
            url: URL of the document to process
            include_image_base64: Whether to include base64-encoded images in the response

        Returns:
            OCR response containing extracted text and metadata
        """
        ocr_response = await self.client.ocr.process_async(
            model=self.model,
            document={
                "type": "document_url",
                "document_url": url,
            },
            include_image_base64=include_image_base64,
        )
        ocr_output = self.ocr_result_from_response(ocr_response=ocr_response)
        return ocr_output

    @override
    async def process_image_url(self, url: str) -> OCROutput:
        """
        Process an image from a URL.

        Args:
            url: URL of the image to process

        Returns:
            OCR response containing extracted text and metadata
        """
        ocr_response = await self.client.ocr.process_async(
            model=self.model,
            document={
                "type": "image_url",
                "image_url": url,
            },
        )
        ocr_output = self.ocr_result_from_response(ocr_response=ocr_response)
        return ocr_output

    @override
    async def process_image_file(self, image_path: str) -> OCROutput:
        """
        Process an image from a local file by encoding it to base64.

        Args:
            image_path: Path to the local image file

        Returns:
            OCR response containing extracted text and metadata
        """
        base64_image = load_image_as_base64_from_path(path=image_path).decode("utf-8")

        ocr_response = await self.client.ocr.process_async(
            model=self.model,
            document={"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"},
        )
        ocr_output = self.ocr_result_from_response(ocr_response=ocr_response)
        return ocr_output

    async def upload_local_document(self, file_path: str) -> str:
        """
        Upload a local file to Mistral.

        Args:
            file_path: Path to the local file to upload

        Returns:
            ID of the uploaded file
        """
        async with aiofiles.open(file_path, "rb") as file:
            file_content = await file.read()

        uploaded_file = await self.client.files.upload_async(
            file={"file_name": os.path.basename(file_path), "content": file_content},
            purpose="ocr",
        )
        return uploaded_file.id

    @override
    async def process_document_file(self, file_path: str) -> OCROutput:
        """
        Upload a file and process it with OCR.

        Args:
            file_path: Path to the local file to upload

        Returns:
            OCR response containing extracted text and metadata
        """
        # Upload the file
        uploaded_file_id = await self.upload_local_document(file_path)

        # Get signed URL
        signed_url = await self.client.files.get_signed_url_async(
            file_id=uploaded_file_id,
        )

        # Process the document
        ocr_response = await self.client.ocr.process_async(
            model=self.model,
            document={
                "type": "document_url",
                "document_url": signed_url.url,
            },
        )
        ocr_output = self.ocr_result_from_response(ocr_response=ocr_response)
        return ocr_output

    def ocr_result_from_response(self, ocr_response: OCRResponse) -> OCROutput:
        full_markdown = "\n".join([page.markdown for page in ocr_response.pages])
        return OCROutput(text=full_markdown)
