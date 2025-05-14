# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel


class Image(BaseModel):
    uri: str
    base_64: Optional[str] = None
    caption: Optional[str] = None


class OCROutput(BaseModel):
    text: str
    images: List[Image]


class OCREngineAbstract(ABC):
    """
    Abstract base class for OCR engines.
    Defines the interface that all OCR implementations should follow.
    """

    async def extract_text_from_image(
        self,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> OCROutput:
        """
        Extract text from an image asynchronously.
        """
        if image_url:
            return await self.process_image_url(url=image_url)
        elif image_path:
            return await self.process_image_file(image_path=image_path)
        else:
            raise ValueError("Either image_path or image_url must be provided")

    async def extract_text_from_pdf(
        self,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
    ) -> OCROutput:
        """
        Extract text from a document asynchronously.
        """
        if pdf_url:
            return await self.process_pdf_url(url=pdf_url)
        elif pdf_path:
            return await self.process_document_file(file_path=pdf_path)
        else:
            raise ValueError("Either pdf_path or pdf_url must be provided")

    @abstractmethod
    async def process_pdf_url(self, url: str, caption_image: bool = False) -> OCROutput:
        """
        Process a document from a URL asynchronously.

        Args:
            url: URL of the document to process

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_image_url(self, url: str, caption_image: bool = False) -> OCROutput:
        """
        Process an image from a URL asynchronously.

        Args:
            url: URL of the image to process

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_image_file(self, image_path: str, caption_image: bool = False) -> OCROutput:
        """
        Process an image from a local file asynchronously.

        Args:
            image_path: Path to the local image file

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_document_file(self, file_path: str, caption_image: bool = False) -> OCROutput:
        """
        Process a document from a local file asynchronously.

        Args:
            file_path: Path to the local document file

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def caption_image(
        self,
        image_uri: str,
    ) -> str:
        """
        Caption an image asynchronously.
        """
        pass
