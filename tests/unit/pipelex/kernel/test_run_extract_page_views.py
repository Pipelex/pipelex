"""`run_extract` refuses page views on a document it knows is not a PDF, before anything is paid for.

Run setup refuses what it is certain of; a step reached through a condition, or a document a previous step produced, gets
here instead. The rule is the page-view renderer's, so it does not depend on the model and needs no worker to reach.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.exceptions import ExtractInputFormatError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.kernel.extract_ops import build_extract_job_params, run_extract
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXTRACT_SETTING = ExtractSetting(model="run-extract-page-views-model")


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_extract_page_views"))


def _extract_stub(mocker: MockerFixture) -> Any:
    page = PageContent(text_and_images=TextAndImagesContent(text=TextContent(text="page")))
    content_generator = mocker.MagicMock()
    content_generator.make_extract_pages = mocker.AsyncMock(return_value=[page])
    mocker.patch("pipelex.kernel.extract_ops.get_content_generator", return_value=content_generator)
    return content_generator.make_extract_pages


async def _run(*, extract_input: ExtractInput, should_include_page_views: bool) -> None:
    await run_extract(
        memory=WorkingMemoryFactory.make_empty(),
        extract_input=extract_input,
        extract_setting=EXTRACT_SETTING,
        extract_job_params=build_extract_job_params(extract_setting=EXTRACT_SETTING, should_include_page_views=should_include_page_views),
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        result_name="pages",
    )


@pytest.mark.asyncio(loop_scope="class")
class TestRunExtractPageViews:
    async def test_a_known_non_pdf_is_refused_before_the_extraction(self, mocker: MockerFixture):
        make_extract_pages = _extract_stub(mocker)

        with pytest.raises(ExtractInputFormatError) as exc_info:
            await _run(
                extract_input=ExtractInput(document_uri="pipelex-storage://report.docx", mime_type=DOCX_MIME, input_name="report"),
                should_include_page_views=True,
            )

        make_extract_pages.assert_not_called()
        assert exc_info.value.message == (
            "Input 'report' is a Word document (.docx), and page views are drawn from a PDF. Give a PDF, or remove page_views from the step."
        )
        assert exc_info.value.to_problem(view=ProblemView.CALLER).to_wire().get("params") == {
            "input": "report",
            "format": "docx",
            "model": "pypdfium2",
        }

    async def test_a_file_no_input_named_is_described_as_the_file_to_extract(self, mocker: MockerFixture):
        _extract_stub(mocker)

        with pytest.raises(ExtractInputFormatError, match=r"^The file to extract is a Word document"):
            await _run(extract_input=ExtractInput(document_uri="pipelex-storage://report.docx", mime_type=DOCX_MIME), should_include_page_views=True)

    @pytest.mark.parametrize(
        ("mime_type", "should_include_page_views"),
        [
            pytest.param("application/pdf", True, id="a-pdf"),
            pytest.param(None, True, id="an-unknown-format-left-to-the-renderer"),
            pytest.param(DOCX_MIME, False, id="no-page-views-asked"),
        ],
    )
    async def test_everything_else_reaches_the_extraction(self, mocker: MockerFixture, mime_type: str | None, should_include_page_views: bool):
        make_extract_pages = _extract_stub(mocker)

        await _run(
            extract_input=ExtractInput(document_uri="pipelex-storage://file", mime_type=mime_type),
            should_include_page_views=should_include_page_views,
        )

        make_extract_pages.assert_awaited_once()

    async def test_an_image_input_is_not_a_document_to_refuse(self, mocker: MockerFixture):
        """An image is its own single page view, without PDFium, whatever its format."""
        make_extract_pages = _extract_stub(mocker)

        await _run(extract_input=ExtractInput(image_uri="pipelex-storage://scan.png", mime_type="image/png"), should_include_page_views=True)

        make_extract_pages.assert_awaited_once()
