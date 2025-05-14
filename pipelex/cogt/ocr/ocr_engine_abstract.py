# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel


class OCREngineInputError(ValueError):
    pass


class OCRExtractedImage(BaseModel):
    uri: str
    base_64: Optional[str] = None
    caption: Optional[str] = None


class OCROutput(BaseModel):
    text: str
    images: List[OCRExtractedImage]


class OCREngineAbstract(ABC):
    """
    Abstract base class for OCR engines.
    Defines the interface that all OCR implementations should follow.
    """

    def _validate_source_params(self, path_param: Optional[str], url_param: Optional[str], resource_type: str) -> None:
        """Helper method to validate source parameters."""
        if path_param and url_param:
            raise OCREngineInputError(f"Either {resource_type}_path or {resource_type}_url must be provided, not both")
        if not (path_param or url_param):
            raise OCREngineInputError(f"Either {resource_type}_path or {resource_type}_url must be provided")

    async def extraction_from_image(
        self,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Launch OCR extraction from an image asynchronously.
        """
        self._validate_source_params(image_path, image_url, "image")

        if image_url:
            return await self.extract_from_image_url(
                image_url=image_url,
                caption_image=caption_image,
            )
        else:  # image_path must be provided based on validation
            assert image_path is not None  # Type narrowing for mypy
            return await self.extract_from_image_file(
                image_path=image_path,
                caption_image=caption_image,
            )

    async def extraction_from_pdf(
        self,
        pdf_path: Optional[str] = None,
        pdf_url: Optional[str] = None,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Launch OCR extraction from a PDF asynchronously.
        """
        self._validate_source_params(pdf_path, pdf_url, "pdf")

        if pdf_url:
            return await self.extract_from_pdf_url(
                pdf_url=pdf_url,
                caption_image=caption_image,
            )
        else:  # pdf_path must be provided based on validation
            assert pdf_path is not None  # Type narrowing for mypy
            return await self.extract_from_pdf_file(
                pdf_path=pdf_path,
                caption_image=caption_image,
            )

    @abstractmethod
    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Process a PDF from a URL asynchronously.

        Args:
            url: URL of the PDF to process
            caption_image: Whether to generate captions for extracted images

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def extract_from_image_url(
        self,
        image_url: str,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Process an image from a URL asynchronously.

        Args:
            url: URL of the image to process
            caption_image: Whether to generate captions for the image

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def extract_from_image_file(
        self,
        image_path: str,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Process an image from a local file asynchronously.

        Args:
            image_path: Path to the local image file
            caption_image: Whether to generate captions for the image

        Returns:
            OCR response containing extracted text and metadata
        """
        pass

    @abstractmethod
    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        caption_image: bool = False,
    ) -> OCROutput:
        """
        Process a PDF from a local file asynchronously.

        Args:
            file_path: Path to the local PDF file
            caption_image: Whether to generate captions for extracted images

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
