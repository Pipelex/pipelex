# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex.cogt.ocr.mistral_ocr import MistralOCREngine
from tests.test_data import PDFTestCases


@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestMistralOCRAsync:
    @pytest.mark.parametrize("file_path", [PDFTestCases.DOCUMENT_FILE_PATH])
    async def test_process_document_file_async(self, file_path: str):
        ocr = MistralOCREngine()
        result = await ocr.extract_from_pdf_file(file_path)
        assert result.pages

    @pytest.mark.parametrize("url", [PDFTestCases.DOCUMENT_URL])
    async def test_process_document_url_async(self, url: str):
        ocr = MistralOCREngine()
        result = await ocr.extract_from_pdf_url(url)
        assert result.pages

    @pytest.mark.parametrize("file_path", [PDFTestCases.IMAGE_FILE_PATH])
    async def test_process_image_file_async(self, file_path: str):
        ocr = MistralOCREngine()
        result = await ocr.extract_from_image_file(file_path)
        assert result.pages

    @pytest.mark.parametrize("url", [PDFTestCases.IMAGE_URL])
    async def test_process_image_url_async(self, url: str):
        ocr = MistralOCREngine()
        result = await ocr.extract_from_image_url(url)
        assert result.pages
