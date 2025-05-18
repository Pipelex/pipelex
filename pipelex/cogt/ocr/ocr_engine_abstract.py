# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod


from pipelex.cogt.ocr.ocr_extraction_models import OcrOutput


class OCREngineInputError(ValueError):
    pass


class OCREngineAbstract(ABC):
    """
    Abstract base class for OCR engines.
    Defines the interface that all OCR implementations should follow.
    """

    @abstractmethod
    async def make_ocr_output_from_image(
        self,
        image_uri: str,
        should_caption_image: bool,
    ) -> OcrOutput:
        pass

    @abstractmethod
    async def make_ocr_output_from_pdf(
        self,
        pdf_uri: str,
        should_caption_images: bool,
        should_add_screenshots: bool,
    ) -> OcrOutput:
        pass
