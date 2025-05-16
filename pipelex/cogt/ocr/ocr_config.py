# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import BaseModel


class MistralOCRConfig(BaseModel):
    ocr_model_name: str


class OCRConfig(BaseModel):
    default_ocr_engine_name: str
    mistral_ocr_config: MistralOCRConfig
