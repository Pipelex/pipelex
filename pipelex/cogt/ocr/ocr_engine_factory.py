# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class OCREngineFactory:
    @staticmethod
    def make_ocr_engine(
        ocr_platform: OcrPlatform,
    ) -> OCREngineAbstract:
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                try:
                    from pipelex.cogt.mistral.mistral_ocr import MistralOCREngine
                except ImportError as exc:
                    raise MissingDependencyError(
                        "mistralai",
                        "mistral",
                        "The mistralai SDK is required to use Mistral OCR through the mistralai client.",
                    ) from exc
                return MistralOCREngine()
