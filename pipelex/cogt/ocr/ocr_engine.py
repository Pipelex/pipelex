# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import BaseModel

from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class OcrEngine(BaseModel):
    ocr_platform: OcrPlatform
    ocr_model_name: str

    @property
    def desc(self) -> str:
        return f"Ocr Engine {self.ocr_platform}/{self.ocr_model_name}"
