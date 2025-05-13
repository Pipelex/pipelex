# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_exceptions import UnsupportedOCREngineError


class OcrEngineName(StrEnum):
    MISTRAL = "mistral"


class OCREngineFactory:
    @staticmethod
    def make_ocr_engine(ocr_model_name: str) -> OCREngineAbstract:
        match ocr_model_name:
            case OcrEngineName.MISTRAL.value:
                try:
                    from pipelex.cogt.ocr.mistral_ocr import MistralOCREngine
                except ImportError as exc:
                    raise MissingDependencyError(
                        "mistralai",
                        "mistral",
                        "The mistralai SDK is required to use Mistral OCR through the mistralai client.",
                    ) from exc
                return MistralOCREngine()
            case _:
                raise UnsupportedOCREngineError(f"Unsupported OCR engine type: {ocr_model_name}")
