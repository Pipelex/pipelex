from pipelex.tools.markdown.markdown_parser import render_markdown_as_html


class TestMarkdownParser:
    def test_only_a_url_with_a_scheme_becomes_a_link(self) -> None:
        html = render_markdown_as_html("See https://example.com/docs, README.md, www.example.com and ada@example.com.")
        assert '<a href="https://example.com/docs">' in html
        assert "README.md" in html
        assert html.count("<a ") == 1

    def test_tables_and_strikethrough_are_formatted(self) -> None:
        html = render_markdown_as_html("| a | b |\n| - | - |\n| 1 | 2 |\n\n~~gone~~")
        assert "<table>" in html
        assert "<s>gone</s>" in html
