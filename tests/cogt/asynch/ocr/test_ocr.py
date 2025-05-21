# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex import pretty_print
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobParams
from pipelex.cogt.ocr.ocr_job_factory import OcrJobFactory
from pipelex.hub import get_ocr_worker
from tests.test_data import ImageTestCases, PDFTestCases


@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestCogtOcr:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_ocr_pdr_path(self, file_path: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=file_path),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")

        assert ocr_output.pages

    @pytest.mark.parametrize("url", PDFTestCases.DOCUMENT_URLS)
    async def test_ocr_url(self, url: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=url),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        assert ocr_output.pages

    @pytest.mark.parametrize("file_path", [ImageTestCases.IMAGE_FILE_PATH])
    async def test_ocr_image_file(self, file_path: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(image_uri=file_path),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        assert ocr_output.pages

    @pytest.mark.parametrize("url", [ImageTestCases.IMAGE_URL])
    async def test_ocr_image_url(self, url: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(image_uri=url),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        assert ocr_output.pages

    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_ocr_image_save(self, file_path: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job_params = OcrJobParams.make_default_ocr_job_params()
        ocr_job_params.should_include_images = True
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=file_path),
            ocr_job_params=ocr_job_params,
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
