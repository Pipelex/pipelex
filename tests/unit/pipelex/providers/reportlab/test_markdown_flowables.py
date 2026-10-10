import re

import pytest
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode
from pytest_mock import MockerFixture
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT  # type: ignore[import-untyped]
from reportlab.platypus import Paragraph  # type: ignore[import-untyped]

from pipelex.cogt.doc_gen.layout_tree import MarkdownBlock
from pipelex.providers.reportlab.markdown_flowables import inline_markup, markdown_nodes_to_flowables
from pipelex.providers.reportlab.pdf_elements import MONO_FONT, build_pdf_styles, data_table
from pipelex.tools.markdown.markdown_parser import get_markdown_parser
from pipelex.tools.markdown.markdown_rules import is_linked_href, plain_text
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import (
    StubRenderResources,
    document_text,
    embedded_font_names,
    link_targets,
    page_texts,
    render_layout,
    render_markdown,
)
from tests.unit.pipelex.providers.reportlab.test_data import MarkdownFlowablesTestData
from tests.unit.pipelex.tools.markdown.test_data import MarkdownFormattingTestData


def _list_lines(*, text: str) -> list[str]:
    """The lines of a text that are list items: a number and a dot, or a bullet, then the item's text."""
    return [line for line in text.splitlines() if re.match(r"^(\d+\.|•|–) ", line)]


def _inline_nodes(*, markdown_text: str) -> list[SyntaxTreeNode]:
    paragraph = SyntaxTreeNode(get_markdown_parser().parse(markdown_text)).children[0]
    return paragraph.children


class TestMarkdownFlowables:
    def test_a_nested_list_numbers_itself_and_keeps_the_outer_numbering(self) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text=MarkdownFlowablesTestData.NESTED_LISTS))
        assert _list_lines(text=text) == ["1. alpha", "2. beta", "1. gamma", "2. delta", "• epsilon", "3. zeta", "4. eta"]

    def test_an_ordered_list_starts_at_its_own_start(self) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text=MarkdownFlowablesTestData.STARTED_LISTS))
        assert _list_lines(text=text) == ["7. seven", "8. eight", "3. three", "4. four", "9. nine"]

    def test_nested_bullets_alternate(self) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text="- one\n  - two\n    - three\n"))
        assert _list_lines(text=text) == ["• one", "– two", "• three"]

    def test_headings_paragraphs_quotes_and_rules_print_their_text_in_order(self) -> None:
        markdown_text = "# Report\n\n## Findings\n\n###### Small print\n\nPlain paragraph.\n\n> Quoted *words*\n\n---\n\nAfter the rule."
        text = document_text(pdf_data=render_markdown(markdown_text=markdown_text))
        assert text.endswith("Report\nFindings\nSmall print\nPlain paragraph.\nQuoted words\nAfter the rule.")

    def test_a_table_prints_its_header_and_cells(self) -> None:
        markdown_text = "| Quarter | Revenue |\n| --- | --: |\n| Q1 | **$1.2M** |\n| Q2 |\n"
        assert "Quarter Revenue\nQ1 $1.2M\nQ2" in document_text(pdf_data=render_markdown(markdown_text=markdown_text))

    def test_a_table_cell_is_aligned_as_its_column_is(self, mocker: MockerFixture) -> None:
        built_table = mocker.patch("pipelex.providers.reportlab.markdown_flowables.data_table", wraps=data_table)
        nodes = SyntaxTreeNode(get_markdown_parser().parse("| L | C | R | N |\n| :-- | :-: | --: | --- |\n| a | b | c | d |\n")).children
        markdown_nodes_to_flowables(nodes=nodes, styles=build_pdf_styles(), available_width=400)
        rows = built_table.call_args.kwargs["rows"]
        assert [[cell.style.alignment for cell in row] for row in rows] == [[TA_LEFT, TA_CENTER, TA_RIGHT, TA_LEFT]] * 2

    def test_a_long_table_repeats_its_header_on_the_next_page(self) -> None:
        rows = "".join(f"| Row {index} | {index * 10} |\n" for index in range(1, 91))
        pages = page_texts(pdf_data=render_markdown(markdown_text=f"| Label | Value |\n| --- | --- |\n{rows}"))
        assert len(pages) >= 2
        for page_text in pages:
            assert "Label Value" in page_text

    def test_a_code_block_prints_as_written_in_the_monospace_face(self) -> None:
        code_line = 'if a < b && c > d: print("<b>**not bold**</b>") # Zażółć Καλημέρα'
        pdf_data = render_markdown(markdown_text=f"```python\n{code_line}\n```\n\n    indented <i>code</i>\n")
        assert document_text(pdf_data=pdf_data).endswith(f"{code_line}\nindented <i>code</i>")
        assert "RobotoMono-Regular" in embedded_font_names(pdf_data=pdf_data)

    def test_a_long_code_line_wraps_inside_the_page(self) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text="```\n" + "x" * 400 + "\n```\n"))
        assert text.count("x") == 400
        assert max(len(line) for line in text.splitlines()) < 400

    def test_bold_italics_strikethrough_and_code_pick_their_faces(self) -> None:
        pdf_data = render_markdown(markdown_text="Some **bold**, some *italic*, some ***both***, ~~struck~~ and `code`.")
        assert "Some bold, some italic, some both, struck and code." in document_text(pdf_data=pdf_data)
        expected_fonts = {"OpenSans-Regular", "OpenSans-Bold", "OpenSans-Italic", "OpenSans-BoldItalic", "RobotoMono-Regular"}
        assert expected_fonts <= embedded_font_names(pdf_data=pdf_data)

    @pytest.mark.parametrize(
        ("markdown_text", "expected_text"),
        [
            (MarkdownFormattingTestData.DEEP_EMPHASIS, MarkdownFormattingTestData.DEEP_EMPHASIS_TEXT),
            (MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS, MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS_TEXT),
        ],
    )
    def test_emphasis_nested_hundreds_deep_prints_its_text(self, markdown_text: str, expected_text: str) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text=markdown_text))
        assert expected_text in " ".join(text.split())

    def test_markup_in_markdown_text_prints_as_written(self) -> None:
        text = document_text(pdf_data=render_markdown(markdown_text="Tom & Jerry say <b>hello</b> &amp; <br/> bye"))
        assert "Tom & Jerry say <b>hello</b> & <br/> bye" in text

    def test_only_web_and_mail_links_become_links(self) -> None:
        markdown_text = (
            "See [the site](https://pipelex.com), [write](mailto:team@pipelex.com), [evil](javascript:alert(1)), "
            "[files](ftp://example.com/file) and https://example.com/auto."
        )
        pdf_data = render_markdown(markdown_text=markdown_text)
        assert sorted(link_targets(pdf_data=pdf_data)) == ["https://example.com/auto", "https://pipelex.com", "mailto:team@pipelex.com"]
        assert "See the site, write, [evil](javascript:alert(1)), files and https://example.com/auto." in document_text(pdf_data=pdf_data)

    @pytest.mark.parametrize(("href", "is_linked"), MarkdownFlowablesTestData.LINK_CASES)
    def test_a_link_target_is_linked_only_for_web_and_mail(self, href: str, is_linked: bool) -> None:
        assert is_linked_href(href=href) is is_linked

    def test_a_link_target_is_escaped_in_the_markup(self) -> None:
        tokens = [Token(type="link_open", tag="a", nesting=1, attrs={"href": 'https://x.com/"><b>'}), Token(type="link_close", tag="a", nesting=-1)]
        markup = inline_markup(nodes=SyntaxTreeNode(tokens).children)
        assert markup == '<a href="https://x.com/&quot;&gt;&lt;b&gt;" color="#1d4ed8"></a>'

    def test_a_markdown_image_prints_its_alt_text_and_is_never_read(self) -> None:
        resources = StubRenderResources()
        markdown_block = MarkdownBlock(markdown="Before ![a *chart* of sales](https://example.com/chart.png) after")
        pdf_data = render_layout(blocks=[markdown_block], resources=resources)
        assert "Before [image: a chart of sales] after" in document_text(pdf_data=pdf_data)
        assert resources.reads == []

    def test_inline_markup_escapes_text_and_tags_emphasis(self) -> None:
        markup = inline_markup(nodes=_inline_nodes(markdown_text="**a < b** and *c & d* and `<e>`"))
        assert markup == f'<b>a &lt; b</b> and <i>c &amp; d</i> and <font face="{MONO_FONT}">&lt;e&gt;</font>'

    def test_unknown_nodes_print_their_text(self) -> None:
        tokens = [
            Token(type="custom_block", tag="div", nesting=0, content="Custom <text>"),
            Token(type="weird_open", tag="x", nesting=1),
            Token(
                type="inline", tag="", nesting=0, content="inner", children=[Token(type="mystery_inline", tag="", nesting=0, content="Inner & text")]
            ),
            Token(type="weird_close", tag="x", nesting=-1),
        ]
        nodes = SyntaxTreeNode(tokens).children
        assert plain_text(nodes=nodes) == "Custom <text>Inner & text"
        flowables = markdown_nodes_to_flowables(nodes=nodes, styles=build_pdf_styles(), available_width=400)
        paragraphs = [flowable for flowable in flowables if isinstance(flowable, Paragraph)]
        assert len(paragraphs) == len(flowables)
        assert [paragraph.getPlainText() for paragraph in paragraphs] == ["Custom <text>", "Inner & text"]
