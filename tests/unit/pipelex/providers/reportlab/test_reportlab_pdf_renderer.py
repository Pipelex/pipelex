from __future__ import annotations

import datetime
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import pytest
from reportlab.platypus import Table  # type: ignore[import-untyped]
from reportlab.platypus.doctemplate import BaseDocTemplate, LayoutError  # type: ignore[import-untyped]

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.cogt.doc_gen.layout_tree import (
    FieldGridBlock,
    ImageBlock,
    LayoutBlock,
    LayoutColumn,
    LayoutDocument,
    LayoutField,
    LayoutScalar,
    MarkdownBlock,
    ParagraphsBlock,
    SectionBlock,
    TableBlock,
)
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.providers.reportlab.reportlab_pdf_renderer import display_scalar
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import (
    TEST_FILENAME,
    TEST_TITLE,
    ResourceRead,
    StubRenderResources,
    document_text,
    embedded_font_names,
    get_test_renderer,
    image_count,
    page_texts,
    pdf_title,
    png_bytes,
    png_data_url,
    render_layout,
)
from tests.unit.pipelex.providers.reportlab.test_data import MARKUP_VALUE, ReportlabRendererTestData, line_items_table

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestReportlabPdfRenderer:
    def test_a_long_table_repeats_its_header_on_the_next_page(self) -> None:
        pages = page_texts(pdf_data=render_layout(blocks=[line_items_table(row_count=90)]))
        assert len(pages) >= 2
        for page_text in pages:
            assert "Description Quantity Amount" in page_text
        assert "Consulting day 1 of the project" in pages[0]
        assert "Consulting day 1 of the project" not in pages[1]
        assert "Consulting day 90 of the project" in pages[-1]

    def test_a_long_table_starts_right_under_its_heading(self) -> None:
        """A table too long for the page is not pushed onto the next page to stay with its heading."""
        pdf_data = render_layout(blocks=[FieldGridBlock(fields=[LayoutField(label="Invoice", value="INV-1")]), line_items_table(row_count=90)])
        first_page = page_texts(pdf_data=pdf_data)[0]
        assert "Line items\nDescription Quantity Amount\nConsulting day 1 of the project" in first_page

    def test_every_page_carries_the_running_header_and_its_number_out_of_the_count(self) -> None:
        pages = page_texts(pdf_data=render_layout(blocks=[line_items_table(row_count=50)], title="Invoice INV-2026-0142"))
        assert len(pages) == 2
        for page_number, page_text in enumerate(pages, start=1):
            assert page_text.startswith(f"Invoice INV-2026-0142\nPage {page_number} of 2\n")

    def test_the_title_prints_first_and_is_the_pdf_title(self) -> None:
        pdf_data = render_layout(blocks=[ParagraphsBlock(paragraphs=["Body"])], title="Quarterly review")
        assert pdf_title(pdf_data=pdf_data) == "Quarterly review"
        assert document_text(pdf_data=pdf_data) == "Quarterly review\nPage 1 of 1\nQuarterly review\nBody"

    @pytest.mark.parametrize(("topic", "blocks"), ReportlabRendererTestData.MARKUP_CASES)
    def test_markup_characters_print_as_written(self, topic: str, blocks: list[LayoutBlock]) -> None:
        assert MARKUP_VALUE in document_text(pdf_data=render_layout(blocks=blocks)), topic

    def test_the_title_prints_its_markup_characters_as_written(self) -> None:
        assert document_text(pdf_data=render_layout(blocks=[], title=MARKUP_VALUE)).count(MARKUP_VALUE) == 2

    @pytest.mark.parametrize(("language", "sample"), ReportlabRendererTestData.SCRIPT_CASES)
    def test_text_beyond_western_european_prints_in_the_bundled_font(self, language: str, sample: str) -> None:
        pdf_data = render_layout(blocks=[ParagraphsBlock(paragraphs=[sample]), FieldGridBlock(fields=[LayoutField(label=language, value=sample)])])
        assert document_text(pdf_data=pdf_data).count(sample) == 2
        assert embedded_font_names(pdf_data=pdf_data) >= {"OpenSans-Regular", "OpenSans-Bold"}

    def test_line_breaks_in_a_paragraph_are_kept(self) -> None:
        text = document_text(pdf_data=render_layout(blocks=[ParagraphsBlock(paragraphs=["1 rue de la Paix\n75002 Paris"])]))
        assert "1 rue de la Paix\n75002 Paris" in text

    def test_deep_sections_print_every_heading(self) -> None:
        innermost: LayoutBlock = ParagraphsBlock(paragraphs=["Deepest text"])
        for level in range(9, 0, -1):
            innermost = SectionBlock(title=f"Section level {level}", level=level, blocks=[innermost])
        text = document_text(pdf_data=render_layout(blocks=[innermost]))
        assert text.endswith("\n".join([*(f"Section level {level}" for level in range(1, 10)), "Deepest text"]))

    def test_an_image_is_read_once_through_the_resources_with_its_position(self) -> None:
        first_url = png_data_url(width=64, height=32)
        second_url = png_data_url(width=32, height=64, color=(200, 40, 40))
        resources = StubRenderResources()
        pdf_data = render_layout(
            blocks=[
                ImageBlock(url=first_url, caption="The first figure"),
                SectionBlock(title="Appendix", level=1, blocks=[ImageBlock(url=second_url, caption=None)]),
            ],
            resources=resources,
        )
        assert resources.reads == [
            ResourceRead(uri=first_url, position="image 1 of the document"),
            ResourceRead(uri=second_url, position="image 2 of the document"),
        ]
        assert image_count(pdf_data=pdf_data) == 2
        assert "The first figure\nAppendix" in document_text(pdf_data=pdf_data)

    def test_a_large_image_is_scaled_into_one_page(self) -> None:
        pdf_data = render_layout(blocks=[ImageBlock(url=png_data_url(width=4000, height=6000), caption="Huge")])
        assert len(page_texts(pdf_data=pdf_data)) == 1
        assert image_count(pdf_data=pdf_data) == 1

    def test_an_image_prints_whatever_type_its_source_declares(self) -> None:
        """Pillow identifies an image from its bytes, so a misleading declared type does not stop it printing."""
        resources = StubRenderResources(answer=png_bytes(width=64, height=32), answer_mime_type="text/plain")
        pdf_data = render_layout(blocks=[ImageBlock(url="pipelex-storage://run/chart", caption=None)], resources=resources)
        assert image_count(pdf_data=pdf_data) == 1

    def test_a_file_that_is_not_an_image_is_refused_with_its_position(self) -> None:
        resources = StubRenderResources(answer=b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        with pytest.raises(DocGenRenderError, match="image 1 of the document") as exc_info:
            render_layout(blocks=[ImageBlock(url="pipelex-storage://run/chart.svg", caption=None)], resources=resources)
        assert exc_info.value.error_domain == ErrorDomain.INPUT

    def test_a_job_that_is_not_a_pdf_from_the_layout_is_refused(self) -> None:
        job = RenderJob(
            format=DocGenFormat.XLSX,
            source=DocGenSource.LAYOUT,
            filename="book.xlsx",
            title=TEST_TITLE,
            layout=LayoutDocument(title=TEST_TITLE, blocks=[]),
        )
        with pytest.raises(DocGenRenderError, match="built-in PDF engine prints a pdf from the auto-layout"):
            get_test_renderer().render(job=job, resources=StubRenderResources())

    def test_a_layout_error_names_the_part_of_the_document_that_did_not_fit(self, mocker: MockerFixture) -> None:
        original_handle_flowable = BaseDocTemplate.handle_flowable

        def refuse_tables(doc_template: Any, flowables: list[Any]) -> None:
            if flowables and isinstance(flowables[0], Table):
                msg = "Flowable too large on page 1"
                raise LayoutError(msg)
            original_handle_flowable(doc_template, flowables)

        mocker.patch.object(BaseDocTemplate, "handle_flowable", autospec=True, side_effect=refuse_tables)
        with pytest.raises(DocGenRenderError) as exc_info:
            render_layout(blocks=[line_items_table(row_count=3)])
        assert str(exc_info.value) == (
            f"The PDF engine cannot print '{TEST_FILENAME}': the table 'Line items' does not fit on an A4 page, "
            "as part of it is taller than a page and cannot be split across pages."
        )
        assert exc_info.value.error_domain == ErrorDomain.INPUT

    @pytest.mark.parametrize(("value", "expected"), ReportlabRendererTestData.SCALAR_CASES)
    def test_a_scalar_prints_plainly(self, value: LayoutScalar, expected: str) -> None:
        assert display_scalar(value=value) == expected

    def test_table_cells_print_their_scalars(self) -> None:
        table = TableBlock(
            title="Mixed",
            path="mixed",
            columns=[LayoutColumn(key="flag", label="Flag"), LayoutColumn(key="day", label="Day"), LayoutColumn(key="count", label="Count")],
            rows=[{"flag": True, "day": datetime.date(2026, 1, 2), "count": 3.0}, {"flag": None, "day": None, "count": None}],
        )
        assert "Flag Day Count\nYes 2026-01-02 3" in document_text(pdf_data=render_layout(blocks=[table]))

    def test_a_table_with_no_rows_says_so(self) -> None:
        table = TableBlock(title="Empty", path="empty", columns=[LayoutColumn(key="name", label="Name")], rows=[])
        assert "Empty\nName\nNo rows." in document_text(pdf_data=render_layout(blocks=[table]))

    def test_renders_from_several_threads_at_once_print_what_one_render_prints(self) -> None:
        """ReportLab subsets fonts through state the registered fonts share, so the engine builds one document at a time."""
        documents: list[list[LayoutBlock]] = [
            [line_items_table(row_count=60), ParagraphsBlock(paragraphs=["Zażółć gęślą jaźń, Καλημέρα κόσμε"])],
            [MarkdownBlock(markdown="# Report\n\n1. **one**\n2. *two*\n\n```\ncode Съешь\n```\n" * 10)],
        ]
        expected_texts = [document_text(pdf_data=render_layout(blocks=blocks)) for blocks in documents]

        def render_document(index: int) -> bytes:
            return render_layout(blocks=documents[index % 2])

        # A tiny switch interval makes the threads interleave inside ReportLab, where a race would show.
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                rendered = list(pool.map(render_document, range(16)))
        finally:
            sys.setswitchinterval(switch_interval)
        # pdfium is not thread-safe, so the texts are read here, one after the other.
        for index, pdf_data in enumerate(rendered):
            assert document_text(pdf_data=pdf_data) == expected_texts[index % 2]
