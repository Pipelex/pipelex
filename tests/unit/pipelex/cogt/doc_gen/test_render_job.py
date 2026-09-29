import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument, ParagraphsBlock
from pipelex.cogt.doc_gen.render_job import RenderJob


def _layout() -> LayoutDocument:
    return LayoutDocument(title="Notice", blocks=[ParagraphsBlock(paragraphs=["Closed on Monday."])])


class TestRenderJob:
    def test_a_job_carries_the_payload_its_source_names(self) -> None:
        job = RenderJob(format=DocGenFormat.PDF, source=DocGenSource.LAYOUT, filename="notice.pdf", title="Notice", layout=_layout())
        assert job.layout is not None

    def test_a_job_without_its_payload_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="missing"):
            RenderJob(format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="notice.pdf", title="Notice", layout=_layout())

    def test_a_job_with_another_source_s_payload_too_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="only its own payload"):
            RenderJob(
                format=DocGenFormat.PDF,
                source=DocGenSource.HTML,
                filename="notice.pdf",
                title="Notice",
                html="<p>Closed</p>",
                layout=_layout(),
            )

    def test_a_stray_field_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RenderJob.model_validate(
                {"format": "pdf", "source": "html", "filename": "notice.pdf", "title": "Notice", "html": "<p/>", "engine": "weasyprint"}
            )

    def test_a_job_round_trips_through_json_with_the_template_as_base64(self) -> None:
        job = RenderJob(
            format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.xlsx",
            title="Invoice",
            template=b"PK\x03\x04 not really a workbook",
            template_name="invoice.xlsx",
            data={"invoice": {"number": "INV-1", "total": 12.5}},
        )

        json_text = job.model_dump_json()

        assert "PK\\u0003" not in json_text
        assert RenderJob.model_validate_json(json_text) == job
