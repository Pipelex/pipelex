import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key, parse_doc_gen_choice_key


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

    def test_every_step_a_format_can_make_has_a_choice_key_that_parses_back(self) -> None:
        for doc_gen_format in DocGenFormat:
            for source in DocGenSource.possible_for(doc_gen_format=doc_gen_format):
                key = doc_gen_choice_key(doc_gen_format=doc_gen_format, source=source)
                assert parse_doc_gen_choice_key(key) == (doc_gen_format, source)
        assert doc_gen_choice_key(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT) == "pdf.layout"

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("pdf", "is not a '<format>.<source>' key"),
            ("html.layout", "is not a '<format>.<source>' key"),
            ("pdf.markdown", "is not a '<format>.<source>' key"),
            ("pdf.template_file", "a pdf is never composed from a template file"),
            ("xlsx.html", "an xlsx is never composed from an HTML template"),
            ("pptx.layout", "a pptx is never composed from the auto-layout of its inputs"),
        ],
    )
    def test_a_choice_key_no_step_makes_is_refused(self, key: str, expected: str) -> None:
        with pytest.raises(ValueError, match=expected):
            parse_doc_gen_choice_key(key)
