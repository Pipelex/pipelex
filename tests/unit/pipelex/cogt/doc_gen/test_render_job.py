import base64
import json

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument, ParagraphsBlock
from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX, RenderJob


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

    def test_an_html_job_carries_the_base_its_relative_urls_join(self) -> None:
        base_url = f"{METHOD_FILE_URL_PREFIX}{'a' * 64}/templates/letter.html"

        job = RenderJob(format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="notice.pdf", title="Notice", html="<p/>", base_url=base_url)

        assert job.base_url == base_url
        assert RenderJob.model_validate_json(job.model_dump_json()) == job

    @pytest.mark.parametrize(
        ("source", "payload", "base_url", "message"),
        [
            pytest.param(DocGenSource.LAYOUT, {"layout": _layout()}, f"{METHOD_FILE_URL_PREFIX}{'a' * 64}/", "has no HTML", id="no_html"),
            pytest.param(
                DocGenSource.HTML, {"html": "<p/>"}, "file:///etc/", "under 'https://method-files.pipelex.invalid/'", id="not_a_method_file"
            ),
        ],
    )
    def test_a_base_url_is_refused_outside_html_and_outside_the_prefix(
        self, source: DocGenSource, payload: dict[str, object], base_url: str, message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            RenderJob.model_validate(
                {"format": "pdf", "source": source, "filename": "notice.pdf", "title": "Notice", "base_url": base_url, **payload}
            )

    def test_a_stray_field_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            RenderJob.model_validate(
                {"format": "pdf", "source": "html", "filename": "notice.pdf", "title": "Notice", "html": "<p/>", "engine": "weasyprint"}
            )

    def test_a_job_round_trips_through_json_with_the_template_as_base64(self) -> None:
        template = b"PK\x03\x04\xfb\xff not really a workbook"
        job = RenderJob(
            format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.xlsx",
            title="Invoice",
            template=template,
            template_name="invoice.xlsx",
            data={"invoice": {"number": "INV-1", "total": 12.5}},
        )

        json_text = job.model_dump_json()

        # Pydantic writes bytes as URL-safe base64, '-' and '_' where standard base64 has '+' and '/'.
        assert json.loads(json_text)["template"] == base64.urlsafe_b64encode(template).decode()
        assert RenderJob.model_validate_json(json_text) == job
