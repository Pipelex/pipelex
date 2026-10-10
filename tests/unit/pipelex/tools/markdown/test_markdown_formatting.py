import pytest
from markdown_it.token import Token
from pytest_mock import MockerFixture

from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, RenderBudget
from pipelex.tools.markdown.markdown_formatting import (
    FormattedBlock,
    FormattedCodeBlock,
    FormattedHeading,
    FormattedListItem,
    FormattedMarkdown,
    FormattedParagraph,
    FormattedRule,
    FormattedSpan,
    FormattedTable,
    LineBreakSpan,
    TextSpan,
    format_markdown_within_budget,
    spans_text,
)
from tests.unit.pipelex.tools.markdown.test_data import MarkdownFormattingTestData


def _formatted(*, markdown: str) -> FormattedMarkdown:
    return format_markdown_within_budget(markdown_text=markdown, budget=RenderBudget(total=DEFAULT_RENDER_BUDGET_UNITS))


def _only_block_spans(*, markdown: str) -> list[FormattedSpan]:
    """The spans of a text that formats into one paragraph."""
    blocks = _formatted(markdown=markdown).blocks
    assert len(blocks) == 1
    paragraph = blocks[0]
    assert isinstance(paragraph, FormattedParagraph)
    return paragraph.spans


def _list_lines(*, markdown: str) -> list[tuple[str, int, str | None, str]]:
    """Each list item of a text, and each paragraph inside one, as its kind, its list depth, its marker and its text."""
    lines: list[tuple[str, int, str | None, str]] = []
    for block in _formatted(markdown=markdown).blocks:
        match block:
            case FormattedListItem():
                lines.append((block.kind, block.list_depth, block.marker, spans_text(spans=block.spans)))
            case FormattedParagraph() if block.list_depth:
                lines.append((block.kind, block.list_depth, None, spans_text(spans=block.spans)))
            case _:
                pass
    return lines


class _StubParser:
    """A parser handing back tokens a test wrote, standing in for the shared parser."""

    def __init__(self, *, tokens: list[Token]) -> None:
        self._tokens = tokens

    def parse(self, *_arguments: object) -> list[Token]:
        return self._tokens


class TestMarkdownFormatting:
    def test_bold_italics_strikethrough_and_code_are_flagged(self) -> None:
        spans = _only_block_spans(markdown="Some **bold**, *italic*, ***both***, ~~struck~~ and `**code**`.")
        assert spans == [
            TextSpan(text="Some "),
            TextSpan(text="bold", bold=True),
            TextSpan(text=", "),
            TextSpan(text="italic", italic=True),
            TextSpan(text=", "),
            TextSpan(text="both", bold=True, italic=True),
            TextSpan(text=", "),
            TextSpan(text="struck", strikethrough=True),
            TextSpan(text=" and "),
            TextSpan(text="**code**", code=True),
            TextSpan(text="."),
        ]

    def test_nested_bullets_alternate_their_markers_by_depth(self) -> None:
        assert _list_lines(markdown="- one\n  - two\n    - three\n- four\n") == [
            ("list_item", 1, "•", "one"),
            ("list_item", 2, "–", "two"),
            ("list_item", 3, "•", "three"),
            ("list_item", 1, "•", "four"),
        ]

    def test_an_ordered_list_numbers_from_its_own_start(self) -> None:
        markdown = "7. seven\n8. eight\n   1. inner one\n   2. inner two\n9. nine\n"
        assert _list_lines(markdown=markdown) == [
            ("list_item", 1, "7.", "seven"),
            ("list_item", 1, "8.", "eight"),
            ("list_item", 2, "1.", "inner one"),
            ("list_item", 2, "2.", "inner two"),
            ("list_item", 1, "9.", "nine"),
        ]

    def test_a_later_paragraph_of_an_item_is_a_paragraph_at_its_list_depth(self) -> None:
        assert _list_lines(markdown="- first\n\n  more about it\n- second\n") == [
            ("list_item", 1, "•", "first"),
            ("paragraph", 1, None, "more about it"),
            ("list_item", 1, "•", "second"),
        ]

    def test_an_item_opening_with_a_nested_list_prints_its_marker_alone(self) -> None:
        assert _list_lines(markdown="1. - inner\n") == [("list_item", 1, "1.", ""), ("list_item", 2, "–", "inner")]

    def test_an_item_opening_with_a_heading_carries_it_beside_its_marker(self) -> None:
        assert _formatted(markdown="1. ## Step *one*\n   Then more.\n- # Title").blocks == [
            FormattedListItem(list_depth=1, marker="1.", heading_level=2, spans=[TextSpan(text="Step "), TextSpan(text="one", italic=True)]),
            FormattedParagraph(list_depth=1, spans=[TextSpan(text="Then more.")]),
            FormattedListItem(list_depth=1, marker="•", heading_level=1, spans=[TextSpan(text="Title")]),
        ]

    @pytest.mark.parametrize(("topic", "markdown", "expected"), MarkdownFormattingTestData.NESTING_CASES)
    def test_a_nested_block_keeps_its_list_and_quote_depths(self, topic: str, markdown: str, expected: list[FormattedBlock]) -> None:
        assert _formatted(markdown=markdown).blocks == expected, topic

    def test_headings_keep_their_level(self) -> None:
        blocks = _formatted(markdown="# Report\n\n## Findings\n\n###### Small *print*").blocks
        assert blocks == [
            FormattedHeading(level=1, spans=[TextSpan(text="Report")]),
            FormattedHeading(level=2, spans=[TextSpan(text="Findings")]),
            FormattedHeading(level=6, spans=[TextSpan(text="Small "), TextSpan(text="print", italic=True)]),
        ]

    def test_a_code_block_keeps_its_lines_as_written(self) -> None:
        code = 'if a < b && c > d:\n\tprint("<b>**not bold**</b>")'
        blocks = _formatted(markdown=f"```python\n{code}\n```\n\n    indented <i>code</i>\n").blocks
        assert blocks == [
            FormattedCodeBlock(lines=["if a < b && c > d:", '    print("<b>**not bold**</b>")']),
            FormattedCodeBlock(lines=["indented <i>code</i>"]),
        ]

    def test_a_quotation_is_its_blocks_at_their_quote_depth(self) -> None:
        blocks = _formatted(markdown="> outer *words*\n>\n> > inner\n").blocks
        assert blocks == [
            FormattedParagraph(quote_depth=1, spans=[TextSpan(text="outer "), TextSpan(text="words", italic=True)]),
            FormattedParagraph(quote_depth=2, spans=[TextSpan(text="inner")]),
        ]

    def test_a_rule_is_a_block_of_its_own(self) -> None:
        blocks = _formatted(markdown="before\n\n---\n\nafter").blocks
        assert blocks == [FormattedParagraph(spans=[TextSpan(text="before")]), FormattedRule(), FormattedParagraph(spans=[TextSpan(text="after")])]

    def test_a_table_marks_its_header_row_and_pads_every_row(self) -> None:
        blocks = _formatted(markdown="| Quarter | Revenue |\n| --- | --- |\n| Q1 | **$1.2M** |\n| Q2 |\n").blocks
        assert len(blocks) == 1
        table = blocks[0]
        assert isinstance(table, FormattedTable)
        assert [row.is_header for row in table.rows] == [True, False, False]
        assert [[cell.spans for cell in row.cells] for row in table.rows] == [
            [[TextSpan(text="Quarter")], [TextSpan(text="Revenue")]],
            [[TextSpan(text="Q1")], [TextSpan(text="$1.2M", bold=True)]],
            [[TextSpan(text="Q2")], []],
        ]

    def test_a_table_cell_is_aligned_as_its_column_is(self) -> None:
        blocks = _formatted(markdown="| L | C | R | N |\n| :-- | :-: | --: | --- |\n| a | b | c | d |\n| e |\n").blocks
        assert len(blocks) == 1
        table = blocks[0]
        assert isinstance(table, FormattedTable)
        assert [[cell.alignment for cell in row.cells] for row in table.rows] == [["left", "center", "right", None]] * 3

    def test_a_soft_break_reads_as_a_space_and_a_hard_break_as_a_break(self) -> None:
        spans = _only_block_spans(markdown="one\ntwo  \nthree\\\nfour")
        assert spans == [TextSpan(text="one two"), LineBreakSpan(), TextSpan(text="three"), LineBreakSpan(), TextSpan(text="four")]

    def test_raw_html_prints_as_text(self) -> None:
        formatted = _formatted(markdown='Tom & Jerry say <b>hello</b> &amp; <br/> bye\n\n<div onclick="steal()">block</div>')
        assert str(formatted) == 'Tom & Jerry say <b>hello</b> & <br/> bye\n<div onclick="steal()">block</div>'

    def test_only_web_and_mail_links_keep_their_target(self) -> None:
        markdown = (
            "See [the site](https://pipelex.com), [the old site](http://pipelex.com), [write](mailto:team@pipelex.com), "
            "[evil](javascript:alert(1)), [files](ftp://example.com/file), [the readme](README.md) and https://example.com/auto."
        )
        spans = _only_block_spans(markdown=markdown)
        linked = [(span.text, span.link) for span in spans if isinstance(span, TextSpan) and span.link is not None]
        assert linked == [
            ("the site", "https://pipelex.com"),
            ("the old site", "http://pipelex.com"),
            ("write", "mailto:team@pipelex.com"),
            ("https://example.com/auto", "https://example.com/auto"),
        ]
        assert (
            spans_text(spans=spans)
            == "See the site, the old site, write, [evil](javascript:alert(1)), files, the readme and https://example.com/auto."
        )

    def test_an_image_prints_its_alt_text_in_italics(self) -> None:
        spans = _only_block_spans(markdown="Before ![a *chart* of sales](https://example.com/chart.png) after")
        assert spans == [TextSpan(text="Before "), TextSpan(text="[image: a chart of sales]", italic=True), TextSpan(text=" after")]

    @pytest.mark.parametrize(
        ("markdown", "expected_text"),
        [
            (MarkdownFormattingTestData.DEEP_EMPHASIS, MarkdownFormattingTestData.DEEP_EMPHASIS_TEXT),
            (MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS, MarkdownFormattingTestData.DEEP_MIXED_EMPHASIS_TEXT),
        ],
    )
    def test_emphasis_nested_hundreds_deep_prints_its_text_emphasized(self, markdown: str, expected_text: str) -> None:
        spans = _only_block_spans(markdown=markdown)
        assert spans_text(spans=spans) == expected_text
        assert all(isinstance(span, TextSpan) and span.italic for span in spans)

    def test_str_is_the_plain_text(self) -> None:
        assert str(_formatted(markdown=MarkdownFormattingTestData.EVERY_BLOCK)) == MarkdownFormattingTestData.EVERY_BLOCK_PLAIN_TEXT

    def test_the_plain_text_indents_every_line_of_a_list_item_s_blocks(self) -> None:
        plain_text = str(_formatted(markdown=MarkdownFormattingTestData.INSIDE_A_LIST_ITEM))
        assert plain_text == MarkdownFormattingTestData.INSIDE_A_LIST_ITEM_PLAIN_TEXT

    def test_a_text_without_markdown_is_its_plain_text(self) -> None:
        assert str(_formatted(markdown="Payment within 30 days, by transfer.")) == "Payment within 30 days, by transfer."

    @pytest.mark.parametrize("markdown", ["", "   ", "\n\n\t\n"])
    def test_an_empty_or_blank_text_formats_into_nothing_and_is_false(self, markdown: str) -> None:
        formatted = _formatted(markdown=markdown)
        assert formatted == FormattedMarkdown(blocks=[])
        assert not formatted
        assert not str(formatted)

    def test_a_text_that_formats_into_a_block_is_true(self) -> None:
        assert _formatted(markdown="Due in *30* days.")
        assert _formatted(markdown="---")

    def test_unknown_nodes_print_their_text(self, mocker: MockerFixture) -> None:
        tokens = [
            Token(type="custom_block", tag="div", nesting=0, content="Custom <text>"),
            Token(type="weird_open", tag="x", nesting=1),
            Token(
                type="inline", tag="", nesting=0, content="inner", children=[Token(type="mystery_inline", tag="", nesting=0, content="Inner & text")]
            ),
            Token(type="weird_close", tag="x", nesting=-1),
        ]
        mocker.patch("pipelex.tools.markdown.markdown_parser.get_markdown_parser", return_value=_StubParser(tokens=tokens))
        assert _formatted(markdown="anything").blocks == [
            FormattedParagraph(spans=[TextSpan(text="Custom <text>")]),
            FormattedParagraph(spans=[TextSpan(text="Inner & text")]),
        ]
