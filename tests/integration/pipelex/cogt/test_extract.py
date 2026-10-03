import pytest

from pipelex import pretty_print
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.exceptions import ExtractInputFormatError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.runtime_hub import get_extract_worker
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.filetype_utils import format_key_from_mime_type
from tests.cases import DocumentTestCases, ImageTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.filterwarnings("ignore:Accessing the 'model_fields' attribute on the instance is deprecated:DeprecationWarning")
class TestExtract:
    @pytest.mark.parametrize("file_path", DocumentTestCases.PDF_FILE_PATHS)
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
            storage_scope=job_metadata.run_metadata.storage_scope,
            extract_output=extract_output,
        )
        assert page_contents
        for page_index, page_content in enumerate(page_contents):
            pretty_print(page_content, title=f"Page {page_index}")

    @pytest.mark.parametrize(("file_path", "mime_type", "expected_phrase"), DocumentTestCases.NON_PDF_DOCUMENT_CASES)
    async def test_extract_non_pdf_document(
        self,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        extract_job_params: ExtractJobParams,
        file_path: str,
        mime_type: str,
        expected_phrase: str,
    ):
        """A model declaring the document's format extracts it; any other refuses it before the provider call."""
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if extract_job_params.should_caption_images and not extract_worker.is_caption_supported:
            msg = f"Image captioning is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        if not (extract_worker.is_pdf_supported or extract_worker.is_web_page_supported):
            msg = f"Document extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=file_path, mime_type=mime_type, input_name="document"),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        format_key = format_key_from_mime_type(mime_type=mime_type)
        if format_key not in extract_worker.inference_model.readable_formats_for_extract:
            with pytest.raises(ExtractInputFormatError, match="Input 'document' is"):
                await extract_worker.extract_pages(extract_job=extract_job)
            return
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        extracted_text = "\n".join(page.text or "" for page in extract_output.pages.values())
        assert expected_phrase in extracted_text

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

    @pytest.mark.parametrize("url", DocumentTestCases.WEB_URLS)
    async def test_extract_web_url(
        self,
        generated_content_factory: GeneratedContentFactory,
        job_metadata: JobMetadata,
        extract_combo: ModelCombo,
        url: str,
    ):
        """Test web page extraction using Linkup fetch API."""
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_web_page_supported:
            msg = f"Web extraction is not supported for this extract worker: '{extract_worker.desc}'"
            pytest.skip(msg)
        extract_job_params = ExtractJobParams(
            max_nb_images=5,
            should_caption_images=False,
            should_include_page_views=False,
            page_views_dpi=None,
            image_min_size=None,
            render_js=False,
            include_raw_html=True,
        )
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=url),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        assert extract_output.pages
        page = next(iter(extract_output.pages.values()))
        assert page.text, "Web extraction should return markdown text"
        pretty_print(page.text, title="Extracted markdown")
        if page.raw_html:
            pretty_print(page.raw_html[:500], title="Raw HTML (first 500 chars)")
        page_contents = await generated_content_factory.make_page_contents(
            storage_scope=job_metadata.run_metadata.storage_scope,
            extract_output=extract_output,
        )
        assert page_contents
        for page_index, page_content in enumerate(page_contents):
            pretty_print(page_content, title=f"Page {page_index}")

    @pytest.mark.parametrize("file_path", DocumentTestCases.PDF_FILE_PATHS)
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
