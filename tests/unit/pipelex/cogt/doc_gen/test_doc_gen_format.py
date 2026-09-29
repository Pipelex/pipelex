import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource


class TestDocGenFormat:
    @pytest.mark.parametrize(
        ("doc_gen_format", "has_template", "expected_source"),
        [
            (DocGenFormat.PDF, False, DocGenSource.LAYOUT),
            (DocGenFormat.PDF, True, DocGenSource.HTML),
            (DocGenFormat.XLSX, False, DocGenSource.LAYOUT),
            (DocGenFormat.XLSX, True, DocGenSource.TEMPLATE_FILE),
            (DocGenFormat.DOCX, True, DocGenSource.TEMPLATE_FILE),
            (DocGenFormat.PPTX, True, DocGenSource.TEMPLATE_FILE),
        ],
    )
    def test_a_step_s_format_and_template_make_its_source(
        self, doc_gen_format: DocGenFormat, has_template: bool, expected_source: DocGenSource
    ) -> None:
        assert DocGenSource.for_step(doc_gen_format=doc_gen_format, has_template=has_template) == expected_source

    def test_only_a_pdf_has_an_html_template_and_only_a_deck_needs_one(self) -> None:
        assert [doc_gen_format for doc_gen_format in DocGenFormat if doc_gen_format.is_template_html] == [DocGenFormat.PDF]
        assert [doc_gen_format for doc_gen_format in DocGenFormat if not doc_gen_format.has_auto_layout] == [DocGenFormat.PPTX]
        assert DocGenFormat.PDF.template_file_suffix == ".html"
        assert DocGenFormat.DOCX.template_file_suffix == ".docx"
        assert DocGenFormat.PDF.mime_type == "application/pdf"
        assert DocGenFormat.XLSX.suffix == "xlsx"
