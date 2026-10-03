"""Docling, as the internal backend declares it, extracts Word, PowerPoint, Excel and HTML files.

`docling-extract-text` declares `docx`, `pptx`, `xlsx` and `html` beside `pdf` and `image`, so a file
of those formats passes the extract worker's format check, and this proves Docling then reads it.
Docling converts these formats with its declarative backends, which need no model download and run
offline, so this runs with the rest of the suite rather than behind the inference markers.
"""

import pytest

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.runtime_hub import get_extract_worker
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.filetype_utils import format_key_from_mime_type
from tests.cases import DocumentTestCases

DOCLING_EXTRACT_HANDLE = "docling-extract-text"


@pytest.mark.asyncio(loop_scope="class")
class TestDoclingDocumentFormats:
    @pytest.mark.parametrize(("file_path", "mime_type", "expected_phrase"), DocumentTestCases.NON_PDF_DOCUMENT_CASES)
    async def test_docling_extracts_the_formats_it_declares(self, job_metadata: JobMetadata, file_path: str, mime_type: str, expected_phrase: str):
        pytest.importorskip("docling")
        extract_worker = get_extract_worker(extract_handle=DOCLING_EXTRACT_HANDLE)
        assert format_key_from_mime_type(mime_type=mime_type) in extract_worker.inference_model.readable_formats_for_extract
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=file_path, mime_type=mime_type, input_name="document"),
            extract_job_params=ExtractJobParams(
                max_nb_images=None,
                should_caption_images=False,
                should_include_page_views=False,
                page_views_dpi=None,
                image_min_size=None,
            ),
            job_metadata=job_metadata,
        )

        extract_output = await extract_worker.extract_pages(extract_job=extract_job)

        extracted_text = "\n".join(page.text or "" for page in extract_output.pages.values())
        assert expected_phrase in extracted_text
