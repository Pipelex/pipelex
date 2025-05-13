# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class OCROutput(BaseModel):
    text: str


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

    @abstractmethod
    async def process_document_url(self, url: str) -> OCROutput:
        """
        Process a document from a URL asynchronously.

        Args:
            url: URL of the document to process

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_image_url(self, url: str) -> OCROutput:
        """
        Process an image from a URL asynchronously.

        Args:
            url: URL of the image to process

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_image_file(self, image_path: str) -> OCROutput:
        """
        Process an image from a local file asynchronously.

        Args:
            image_path: Path to the local image file

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def process_document_file(self, file_path: str) -> OCROutput:
        """
        Process a document from a local file asynchronously.

        Args:
            file_path: Path to the local document file

        Returns:
            OCR response containing extracted text and metadata
        """
        pass
