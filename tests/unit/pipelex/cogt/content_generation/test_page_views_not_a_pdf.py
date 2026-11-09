"""A file PDFium cannot open fails as an input error saying page views need a PDF, and before the extraction is paid for."""

import base64
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import RenderPageViewsAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.render_generate import render_page_views_and_store
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.pdf.exceptions import PdfDocumentUnreadableError
from tests.cases import DocumentTestCases

DOCX_DATA_URL = "data:application/octet-stream;base64," + base64.b64encode(Path(DocumentTestCases.DOCX_FILE_PATH_1).read_bytes()).decode("ascii")


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_page_views_not_a_pdf"))


def _render_assignment(*, input_name: str | None) -> RenderPageViewsAssignment:
    return RenderPageViewsAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        document_uri=DOCX_DATA_URL,
        page_views_dpi=72,
        input_name=input_name,
    )


def _page_views_params() -> ExtractJobParams:
    return ExtractJobParams.make_default_extract_job_params().model_copy(update={"should_include_page_views": True, "page_views_dpi": 72})


async def _make_extract_pages(*, content_generator: ContentGenerator) -> list[PageContent]:
    return await content_generator.make_extract_pages(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        extract_input=ExtractInput(document_uri="https://example.com/report", input_name="report"),
        extract_handle="page-views-order-model",
        extract_job_params=_page_views_params(),
        extract_job_config=ExtractJobConfig(),
    )


def _content_generator(mocker: MockerFixture) -> ContentGenerator:
    return ContentGenerator(generated_content_factory=mocker.MagicMock(spec=GeneratedContentFactory))


@pytest.mark.asyncio(loop_scope="class")
class TestPageViewsNotAPdf:
    async def test_a_file_pdfium_cannot_open_is_an_unreadable_input_naming_it(self, mocker: MockerFixture):
        with pytest.raises(PdfDocumentUnreadableError) as exc_info:
            await render_page_views_and_store(render_assignment=_render_assignment(input_name="report"), generated_content_factory=mocker.MagicMock())

        problem = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert problem["code"] == CoreCode.INPUT_FILE_UNREADABLE
        assert problem.get("params") == {"input": "report", "file_type": "pdf", "reason": "pdf_load_failed"}, problem
        assert "Page views are drawn from a PDF" in exc_info.value.message
        assert "Data format error" in exc_info.value.message

    async def test_a_url_no_input_gave_names_no_input(self, mocker: MockerFixture):
        with pytest.raises(PdfDocumentUnreadableError) as exc_info:
            await render_page_views_and_store(render_assignment=_render_assignment(input_name=None), generated_content_factory=mocker.MagicMock())

        assert exc_info.value.input_name is None

    async def test_a_refused_render_is_not_paid_for(self, mocker: MockerFixture):
        extract = mocker.patch("pipelex.cogt.content_generation.content_generator.extract_gen_pages_and_store", new=mocker.AsyncMock())
        mocker.patch(
            "pipelex.cogt.content_generation.content_generator.render_page_views_and_store",
            new=mocker.AsyncMock(side_effect=PdfDocumentUnreadableError("not a pdf")),
        )

        with pytest.raises(PdfDocumentUnreadableError):
            await _make_extract_pages(content_generator=_content_generator(mocker))

        extract.assert_not_called()

    async def test_page_views_are_rendered_before_the_extraction_and_attached_to_its_pages(self, mocker: MockerFixture):
        calls: list[str] = []
        page = PageContent(text_and_images=TextAndImagesContent(text=TextContent(text="page")))
        page_view = ImageContent(url="pipelex-storage://view.png")

        def _render(**_kwargs: Any) -> list[ImageContent]:
            calls.append("render")
            return [page_view]

        def _extract(**_kwargs: Any) -> list[PageContent]:
            calls.append("extract")
            return [page]

        mocker.patch("pipelex.cogt.content_generation.content_generator.render_page_views_and_store", new=mocker.AsyncMock(side_effect=_render))
        mocker.patch("pipelex.cogt.content_generation.content_generator.extract_gen_pages_and_store", new=mocker.AsyncMock(side_effect=_extract))

        pages = await _make_extract_pages(content_generator=_content_generator(mocker))

        assert calls == ["render", "extract"]
        assert pages[0].page_view == page_view
