import pytest

from pipelex import pretty_print
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.hub import get_extract_worker, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import DocumentTestCases, ImageTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.filterwarnings("ignore:Accessing the 'model_fields' attribute on the instance is deprecated:DeprecationWarning")
class TestExtract:
    @pytest.mark.parametrize("file_path", DocumentTestCases.DOCUMENT_FILE_PATHS)
    async def test_extract_pdf_path(
        self,
        generated_content_factory: GeneratedContentFactory,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        extract_job_params: ExtractJobParams,
        file_path: str,
    ):
        pretty_print(extract_job_params, title=f"Extract Job Params for {file_path}")
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_pdf_supported:
            msg = f"PDF extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        if extract_job_params.should_caption_images and not extract_worker.is_caption_supported:
            msg = f"Image captioning is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=file_path),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        assert extract_output.pages
        page_contents = await generated_content_factory.make_page_contents(
            primary_id=job_metadata.user_id,
            secondary_id=job_metadata.pipeline_run_id,
            extract_output=extract_output,
        )
        assert page_contents
        for page_index, page_content in enumerate(page_contents):
            pretty_print(page_content, title=f"Page {page_index}")
        get_report_delegate().generate_report()

    @pytest.mark.parametrize("url", DocumentTestCases.DOCUMENT_URLS)
    async def test_extract_pdf_url(
        self,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        extract_job_params: ExtractJobParams,
        url: str,
    ):
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_pdf_supported:
            msg = f"PDF extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        if extract_job_params.should_caption_images and not extract_worker.is_caption_supported:
            msg = f"Image captioning is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=url),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        assert extract_output.pages
        for page_index, page in extract_output.pages.items():
            pretty_print(page.text, title=f"Page {page_index}")

    @pytest.mark.parametrize("file_path", ImageTestCases.IMAGE_TEXT_FILE_PATHS)
    async def test_extract_image_path(
        self,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        extract_job_params: ExtractJobParams,
        file_path: str,
    ):
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_image_supported:
            msg = f"Image extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        if extract_job_params.should_caption_images and not extract_worker.is_caption_supported:
            msg = f"Image captioning is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(image_uri=file_path),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="Extract Output")
        assert extract_output.pages

    @pytest.mark.parametrize("url", ImageTestCases.IMAGE_URLS)
    async def test_extract_image_url(
        self,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        extract_job_params: ExtractJobParams,
        url: str,
    ):
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_image_supported:
            msg = f"Image extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        if extract_job_params.should_caption_images and not extract_worker.is_caption_supported:
            msg = f"Image captioning is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(image_uri=url),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="Extract Output")
        assert extract_output.pages

    @pytest.mark.parametrize("file_path", DocumentTestCases.DOCUMENT_FILE_PATHS)
    async def test_extract_image_save(
        self,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        file_path: str,
    ):
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_pdf_supported:
            msg = f"PDF extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        specific_extract_job_params = ExtractJobParams(
            max_nb_images=None,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=72,
            image_min_size=None,
        )
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=file_path),
            extract_job_params=specific_extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        pretty_print(extract_output, title="Extract Output")
