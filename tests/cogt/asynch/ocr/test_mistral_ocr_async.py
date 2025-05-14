# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex.cogt.ocr.mistral_ocr import MistralOCREngine
from tests.cogt.test_data import OCRTestCases


# TODO: create a new marker specifically for ocr, like we have for llm and imggg
class TestMistralOCRAsync:
    @pytest.mark.asyncio
    @pytest.mark.inference
    async def test_process_document_file_async(self):
        ocr = MistralOCREngine()
        result = await ocr.process_document_file(OCRTestCases.DOCUMENT_FILE_PATH)
        assert result.text

    @pytest.mark.asyncio
    @pytest.mark.inference
    async def test_process_document_url_async(self):
        ocr = MistralOCREngine()
        result = await ocr.process_pdf_url(OCRTestCases.DOCUMENT_URL)
        assert result.text

    @pytest.mark.asyncio
    @pytest.mark.inference
    async def test_process_image_file_async(self):
        ocr = MistralOCREngine()
        result = await ocr.process_image_file(OCRTestCases.IMAGE_FILE_PATH)
        assert result.text

    @pytest.mark.asyncio
    @pytest.mark.inference
    async def test_process_image_url_async(self):
        ocr = MistralOCREngine()
        result = await ocr.process_image_url(OCRTestCases.IMAGE_URL)
        assert result.text
