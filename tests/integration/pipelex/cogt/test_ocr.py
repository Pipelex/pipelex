import pytest

from pipelex import pretty_print
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobParams
from pipelex.cogt.ocr.ocr_job_factory import OcrJobFactory
from pipelex.config import get_config
from pipelex.hub import get_ocr_worker
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from tests.cases import ImageTestCases, PDFTestCases


@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestOcr:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_ocr_pdf_path(self, file_path: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=file_path),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")

        assert ocr_output.pages

    @pytest.mark.parametrize("url", PDFTestCases.DOCUMENT_URLS)
    async def test_ocr_pdf_url(self, url: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=url),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        assert ocr_output.pages

    @pytest.mark.parametrize("file_path", ImageTestCases.IMAGE_FILE_PATHS)
    async def test_ocr_image_file(self, file_path: str):
        ocr_worker = get_ocr_worker(ocr_handle=OcrHandle.MISTRAL_OCR)
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(image_uri=file_path),
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        assert ocr_output.pages

    @pytest.mark.parametrize("url", ImageTestCases.IMAGE_URLS)
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
        ocr_job_params = OcrJobParams(
            should_include_images=True,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=72,
        )
        ocr_job = OcrJobFactory.make_ocr_job(
            ocr_input=OcrInput(pdf_uri=file_path),
            ocr_job_params=ocr_job_params,
        )
        ocr_output = await ocr_worker.ocr_extract_pages(ocr_job=ocr_job)
        pretty_print(ocr_output, title="OCR Output")
        directory = get_incremental_directory_path(
            base_path="results/test_ocr_image_save",
            base_name="ocr_output",
        )
        ocr_output.save_to_directory(
            directory=directory,
            page_text_file_name=get_config().cogt.ocr_config.page_output_text_file_name,
        )
