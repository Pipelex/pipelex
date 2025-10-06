import pytest

from pipelex import pretty_print
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.config import get_config
from pipelex.hub import get_extract_worker
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from tests.cases import ImageTestCases, PDFTestCases


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestExtract:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_extract_pdf_path(self, extract_handle: str, file_path: str):
        extract_worker = get_extract_worker(extract_handle=extract_handle)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(pdf_uri=file_path),
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="Extract Output")

        assert extract_output.pages

    @pytest.mark.parametrize("url", PDFTestCases.DOCUMENT_URLS)
    async def test_extract_pdf_url(self, extract_handle: str, url: str):
        extract_worker = get_extract_worker(extract_handle=extract_handle)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(pdf_uri=url),
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="OCR Output")
        assert extract_output.pages

    @pytest.mark.parametrize("file_path", ImageTestCases.IMAGE_FILE_PATHS)
    async def test_extract_image_file(self, extract_handle_from_image: str, file_path: str):
        extract_worker = get_extract_worker(extract_handle=extract_handle_from_image)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(image_uri=file_path),
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="OCR Output")
        assert extract_output.pages

    @pytest.mark.parametrize("url", ImageTestCases.IMAGE_URLS)
    async def test_extract_image_url(self, extract_handle_from_image: str, url: str):
        extract_worker = get_extract_worker(extract_handle=extract_handle_from_image)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(image_uri=url),
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="OCR Output")
        assert extract_output.pages

    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_extract_image_save(self, extract_handle_from_image: str, file_path: str):
        extract_worker = get_extract_worker(extract_handle=extract_handle_from_image)
        extract_job_params = ExtractJobParams(
            should_include_images=True,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=72,
            max_nb_images=None,
            image_min_size=None,
        )
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(pdf_uri=file_path),
            extract_job_params=extract_job_params,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="OCR Output")
        directory = get_incremental_directory_path(
            base_path="results/test_ocr_image_save",
            base_name="extract_output",
        )
        extract_output.save_to_directory(
            directory=directory,
            page_text_file_name=get_config().cogt.extract_config.page_output_text_file_name,
        )
