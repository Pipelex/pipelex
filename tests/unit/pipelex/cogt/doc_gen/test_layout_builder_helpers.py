from pipelex.cogt.doc_gen.layout_builder import html_to_paragraphs, humanize


class TestLayoutBuilderHelpers:
    def test_humanize(self) -> None:
        assert humanize("unit_price") == "Unit price"
        assert humanize("lineItems") == "LineItems"
        assert humanize("_") == "_"

    def test_html_to_paragraphs_breaks_on_block_tags_and_hides_scripts(self) -> None:
        assert html_to_paragraphs("<ul><li>one</li><li>two &amp; three</li></ul><style>p {}</style><script>hidden</script>") == ["one", "two & three"]

    def test_html_to_paragraphs_keeps_a_table_row_on_one_line_with_its_cells_apart(self) -> None:
        html = "<table><tr><th>Name</th><th>City</th></tr><tr><td>Ada</td><td>London</td></tr></table><dl><dt>Term</dt><dd>Meaning</dd></dl>"
        assert html_to_paragraphs(html) == ["Name | City", "Ada | London", "Term", "Meaning"]
