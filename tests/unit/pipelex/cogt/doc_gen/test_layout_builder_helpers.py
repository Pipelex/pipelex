from pipelex.cogt.doc_gen.layout_builder import html_to_paragraphs, humanize


class TestLayoutBuilderHelpers:
    def test_humanize(self) -> None:
        assert humanize("unit_price") == "Unit price"
        assert humanize("lineItems") == "LineItems"
        assert humanize("_") == "_"

    def test_html_to_paragraphs_breaks_on_block_tags_and_hides_scripts(self) -> None:
        assert html_to_paragraphs("<ul><li>one</li><li>two &amp; three</li></ul><style>p {}</style>") == ["one", "two & three"]
