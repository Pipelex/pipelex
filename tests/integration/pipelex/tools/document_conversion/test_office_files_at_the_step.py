import base64
import uuid
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.stuffs.page_content import PageContent
from pipelex.interpreter_hub import get_pipe_router
from pipelex.kernel import document_conversion_ops
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.document_conversion.document_converter_protocol import DocumentConverterProtocol
from pipelex.tools.document_conversion.readable_pdf import PdfOrigin, ReadablePdf
from tests.integration.pipelex.tools.document_conversion.test_data import DocumentConversionTestData, OfficeFileCase

_OFFICE_FILES_MTHDS = """
domain = "office_files_at_the_step"
description = "Read Office files through a document converter"

[pipe.draw_and_extract]
type = "PipeExtract"
description = "Extract a document with a model reading PDF only, and draw its page views"
inputs = { report = "Document" }
output = "Page[]"
model = "pypdfium2-extract-pdf"
page_views = true

[pipe.name_the_candidate]
type = "PipeLLM"
description = "Read a CV and name the candidate"
inputs = { cv = "Document" }
output = "Text"
model = "$vision-cheap"
prompt = \"\"\"
Whose CV is this? Answer with the person's full name only, nothing else.
$cv
\"\"\"
"""


_STORAGE_SCOPE = "test/office-files-at-the-step"


def _data_url(*, office_file: OfficeFileCase) -> str:
    """The file inline, with no type declared: run setup sniffs its format, as it does a caller's upload."""
    raw_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / office_file.file_name).read_bytes()
    return f"data:application/octet-stream;base64,{base64.b64encode(raw_bytes).decode('ascii')}"


@pytest.mark.document_conversion
@pytest.mark.asyncio(loop_scope="class")
class TestOfficeFilesAtTheStep:
    @pytest.mark.parametrize("office_file", DocumentConversionTestData.OFFICE_FILES, ids=lambda case: case.file_name)
    async def test_an_extraction_with_page_views_reads_the_office_file_as_its_pdf(
        self, mocker: MockerFixture, runtime_document_converter: DocumentConverterProtocol, office_file: OfficeFileCase
    ) -> None:
        """Run setup accepts the file, the step converts it once, and a second run reads the PDF the first one kept beside it."""
        read_document_as_pdf = mocker.spy(document_conversion_ops, "read_document_as_pdf")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        # The file uploaded once, under a key of its own, so that no earlier session's PDF stands beside it.
        source_key = f"{_STORAGE_SCOPE}/assets/{uuid.uuid4().hex}/{office_file.file_name}"
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / office_file.file_name).read_bytes()
        await get_storage_provider().store(data=source_bytes, key=source_key)

        readable_pdfs: list[ReadablePdf] = []
        for _run in range(2):
            pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
                storage_scope=_STORAGE_SCOPE,
                read_scope=None,
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_OFFICE_FILES_MTHDS],
                pipe_code="draw_and_extract",
                pipe_run_mode=PipeRunMode.LIVE,
                inputs={"report": f"pipelex-storage://{source_key}"},
            )
            pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

            pages = pipe_output.main_stuff_as_items(item_type=PageContent)
            assert len(pages) == office_file.page_count
            assert all(page.page_view is not None for page in pages)
            first_page_text = pages[0].text_and_images.text.text if pages[0].text_and_images.text else ""
            for word in office_file.first_page_words:
                assert word in first_page_text
            readable_pdfs.append(read_document_as_pdf.spy_return)
            assert read_document_as_pdf.call_args.kwargs["input_name"] == "report"
            assert read_document_as_pdf.call_args.kwargs["format_key"] == office_file.format_key

        made, kept = readable_pdfs
        assert made.pdf_uri == kept.pdf_uri == f"pipelex-storage://{source_key}.pdf"
        assert (made.origin, kept.origin) == (PdfOrigin.MADE, PdfOrigin.KEPT)
        assert made.converter_name == runtime_document_converter.converter_name
        # The kept PDF is read back with the version the conversion stamped on it.
        assert made.converter_version
        assert made.converter_version == kept.converter_version
        assert (made.page_count, kept.page_count) == (office_file.page_count, office_file.page_count)
        assert made.conversion_seconds is not None
        assert kept.conversion_seconds is None

    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.usefixtures("runtime_document_converter")
    async def test_an_llm_step_reads_a_word_cv_as_its_pdf(self, mocker: MockerFixture, pipe_run_mode: PipeRunMode) -> None:
        """The CV reaches a model that reads PDFs only as its PDF, and the model reads it."""
        if not pipe_run_mode.is_live:
            pytest.skip("a dry run converts nothing")
        read_document_as_pdf = mocker.spy(document_conversion_ops, "read_document_as_pdf")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
        cv = next(office_file for office_file in DocumentConversionTestData.OFFICE_FILES if office_file.format_key == "docx")

        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="test/office-files-at-the-step",
            read_scope=None,
            user_id="test-user",
            execution_config=execution_config,
            mthds_contents=[_OFFICE_FILES_MTHDS],
            pipe_code="name_the_candidate",
            pipe_run_mode=pipe_run_mode,
            inputs={"cv": _data_url(office_file=cv)},
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        read_document_as_pdf.assert_called_once()
        assert read_document_as_pdf.call_args.kwargs["input_name"] == "cv"
        assert "elias thorne" in pipe_output.main_stuff_as_str.lower()
