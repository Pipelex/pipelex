import tracemalloc

import pytest
from jinja2.exceptions import TemplateError
from markdown_it.token import Token
from pytest_mock import MockerFixture

from pipelex.cogt.doc_gen.exceptions import MarkdownFormattingBudgetError
from pipelex.cogt.doc_gen.formatted_markdown import (
    FormattedCodeBlock,
    FormattedHeading,
    FormattedListItem,
    FormattedMarkdown,
    FormattedParagraph,
    FormattedQuotation,
    FormattedRule,
    FormattedSpan,
    FormattedTable,
    LineBreakSpan,
    TextSpan,
    format_markdown,
    spans_text,
)
from pipelex.tools.jinja2.jinja2_render_budget import (
    DEFAULT_RENDER_BUDGET_UNITS,
    RenderBudget,
    RenderBudgetExceededError,
    active_render_budget,
    spending_from,
)
from tests.unit.pipelex.cogt.doc_gen.test_data import FormattedMarkdownTestData

# What a conversion refused for its tables may hold before the refusal: its source and the scan of its lines, never the
# tokens of its cells, which take tens of megabytes here.
_REFUSED_BEFORE_PARSING_PEAK_BYTES = 4 * 1024 * 1024


def _only_block_spans(*, markdown: str) -> list[FormattedSpan]:
    """The spans of a text that formats into one paragraph."""
    blocks = format_markdown(markdown=markdown).blocks
    assert len(blocks) == 1
    paragraph = blocks[0]
    assert isinstance(paragraph, FormattedParagraph)
    return paragraph.spans


def _list_items(*, markdown: str) -> list[tuple[int, str | None, str]]:
    """Each list item of a text as its depth, its marker and its text."""
    return [
        (block.depth, block.marker, spans_text(spans=block.spans))
        for block in format_markdown(markdown=markdown).blocks
        if isinstance(block, FormattedListItem)
    ]


class _StubParser:
    """A parser handing back tokens a test wrote, standing in for the shared parser."""

    def __init__(self, *, tokens: list[Token]) -> None:
        self._tokens = tokens

    def parse(self, *_arguments: object) -> list[Token]:
        return self._tokens


class TestFormattedMarkdown:
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
        assert _list_items(markdown="- one\n  - two\n    - three\n- four\n") == [
            (1, "•", "one"),
            (2, "–", "two"),
            (3, "•", "three"),
            (1, "•", "four"),
        ]

    def test_an_ordered_list_numbers_from_its_own_start(self) -> None:
        markdown = "7. seven\n8. eight\n   1. inner one\n   2. inner two\n9. nine\n"
        assert _list_items(markdown=markdown) == [
            (1, "7.", "seven"),
            (1, "8.", "eight"),
            (2, "1.", "inner one"),
            (2, "2.", "inner two"),
            (1, "9.", "nine"),
        ]

    def test_a_later_paragraph_of_an_item_has_no_marker(self) -> None:
        assert _list_items(markdown="- first\n\n  more about it\n- second\n") == [(1, "•", "first"), (1, None, "more about it"), (1, "•", "second")]

    def test_an_item_opening_with_a_nested_list_prints_its_marker_alone(self) -> None:
        assert _list_items(markdown="1. - inner\n") == [(1, "1.", ""), (2, "–", "inner")]

    def test_headings_keep_their_level(self) -> None:
        blocks = format_markdown(markdown="# Report\n\n## Findings\n\n###### Small *print*").blocks
        assert blocks == [
            FormattedHeading(level=1, spans=[TextSpan(text="Report")]),
            FormattedHeading(level=2, spans=[TextSpan(text="Findings")]),
            FormattedHeading(level=6, spans=[TextSpan(text="Small "), TextSpan(text="print", italic=True)]),
        ]

    def test_a_code_block_keeps_its_lines_as_written(self) -> None:
        code = 'if a < b && c > d:\n\tprint("<b>**not bold**</b>")'
        blocks = format_markdown(markdown=f"```python\n{code}\n```\n\n    indented <i>code</i>\n").blocks
        assert blocks == [
            FormattedCodeBlock(lines=["if a < b && c > d:", '    print("<b>**not bold**</b>")']),
            FormattedCodeBlock(lines=["indented <i>code</i>"]),
        ]

    def test_a_quotation_keeps_its_depth(self) -> None:
        blocks = format_markdown(markdown="> outer *words*\n>\n> > inner\n").blocks
        assert blocks == [
            FormattedQuotation(depth=1, spans=[TextSpan(text="outer "), TextSpan(text="words", italic=True)]),
            FormattedQuotation(depth=2, spans=[TextSpan(text="inner")]),
        ]

    def test_a_rule_is_a_block_of_its_own(self) -> None:
        blocks = format_markdown(markdown="before\n\n---\n\nafter").blocks
        assert blocks == [FormattedParagraph(spans=[TextSpan(text="before")]), FormattedRule(), FormattedParagraph(spans=[TextSpan(text="after")])]

    def test_a_table_marks_its_header_row_and_pads_every_row(self) -> None:
        blocks = format_markdown(markdown="| Quarter | Revenue |\n| --- | --: |\n| Q1 | **$1.2M** |\n| Q2 |\n").blocks
        assert len(blocks) == 1
        table = blocks[0]
        assert isinstance(table, FormattedTable)
        assert [row.is_header for row in table.rows] == [True, False, False]
        assert [[cell.spans for cell in row.cells] for row in table.rows] == [
            [[TextSpan(text="Quarter")], [TextSpan(text="Revenue")]],
            [[TextSpan(text="Q1")], [TextSpan(text="$1.2M", bold=True)]],
            [[TextSpan(text="Q2")], []],
        ]

    def test_a_soft_break_reads_as_a_space_and_a_hard_break_as_a_break(self) -> None:
        spans = _only_block_spans(markdown="one\ntwo  \nthree\\\nfour")
        assert spans == [TextSpan(text="one two"), LineBreakSpan(), TextSpan(text="three"), LineBreakSpan(), TextSpan(text="four")]

    def test_raw_html_prints_as_text(self) -> None:
        formatted = format_markdown(markdown='Tom & Jerry say <b>hello</b> &amp; <br/> bye\n\n<div onclick="steal()">block</div>')
        assert str(formatted) == 'Tom & Jerry say <b>hello</b> & <br/> bye\n<div onclick="steal()">block</div>'

    def test_only_web_and_mail_links_keep_their_target(self) -> None:
        markdown = (
            "See [the site](https://pipelex.com), [the old site](http://pipelex.com), [write](mailto:team@pipelex.com), "
            "[evil](javascript:alert(1)), [files](ftp://example.com/file) and https://example.com/auto."
        )
        spans = _only_block_spans(markdown=markdown)
        linked = [(span.text, span.link) for span in spans if isinstance(span, TextSpan) and span.link is not None]
        assert linked == [
            ("the site", "https://pipelex.com"),
            ("the old site", "http://pipelex.com"),
            ("write", "mailto:team@pipelex.com"),
            ("https://example.com/auto", "https://example.com/auto"),
        ]
        assert spans_text(spans=spans) == "See the site, the old site, write, [evil](javascript:alert(1)), files and https://example.com/auto."

    def test_an_image_prints_its_alt_text_in_italics(self) -> None:
        spans = _only_block_spans(markdown="Before ![a *chart* of sales](https://example.com/chart.png) after")
        assert spans == [TextSpan(text="Before "), TextSpan(text="[image: a chart of sales]", italic=True), TextSpan(text=" after")]

    def test_str_is_the_plain_text(self) -> None:
        assert str(format_markdown(markdown=FormattedMarkdownTestData.EVERY_BLOCK)) == FormattedMarkdownTestData.EVERY_BLOCK_PLAIN_TEXT

    def test_a_text_without_markdown_is_its_plain_text(self) -> None:
        assert str(format_markdown(markdown="Payment within 30 days, by transfer.")) == "Payment within 30 days, by transfer."

    def test_an_empty_text_formats_into_nothing(self) -> None:
        formatted = format_markdown(markdown="")
        assert formatted == FormattedMarkdown(blocks=[])
        assert not str(formatted)

    def test_unknown_nodes_print_their_text(self, mocker: MockerFixture) -> None:
        tokens = [
            Token(type="custom_block", tag="div", nesting=0, content="Custom <text>"),
            Token(type="weird_open", tag="x", nesting=1),
            Token(
                type="inline", tag="", nesting=0, content="inner", children=[Token(type="mystery_inline", tag="", nesting=0, content="Inner & text")]
            ),
            Token(type="weird_close", tag="x", nesting=-1),
        ]
        mocker.patch("pipelex.cogt.doc_gen.formatted_markdown.get_markdown_parser", return_value=_StubParser(tokens=tokens))
        assert format_markdown(markdown="anything").blocks == [
            FormattedParagraph(spans=[TextSpan(text="Custom <text>")]),
            FormattedParagraph(spans=[TextSpan(text="Inner & text")]),
        ]

    def test_outside_a_render_its_own_budget_refuses_a_padded_table_before_parsing_it(self) -> None:
        tracemalloc.start()
        try:
            with pytest.raises(MarkdownFormattingBudgetError, match="outside a template render"):
                format_markdown(markdown=FormattedMarkdownTestData.PADDED_TABLE)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak_bytes < _REFUSED_BEFORE_PARSING_PEAK_BYTES
        assert active_render_budget() is None

    def test_a_reference_used_thousands_of_times_is_refused_before_it_is_built(self) -> None:
        with pytest.raises(MarkdownFormattingBudgetError):
            format_markdown(markdown=FormattedMarkdownTestData.REUSED_REFERENCE)

    def test_outside_a_render_an_ordinary_long_text_formats(self) -> None:
        formatted = format_markdown(markdown=FormattedMarkdownTestData.LONG_REPORT)
        assert sum(isinstance(block, FormattedHeading) for block in formatted.blocks) == 300

    def test_the_budget_error_is_the_caller_s(self) -> None:
        with pytest.raises(MarkdownFormattingBudgetError) as caught:
            format_markdown(markdown=FormattedMarkdownTestData.PADDED_TABLE)
        report = caught.value.to_error_report()
        assert report.error_domain == "input"
        assert report.caller_facing_message
        assert f"{DEFAULT_RENDER_BUDGET_UNITS:,} work units" in caught.value.message

    def test_inside_a_render_the_render_s_budget_is_charged(self) -> None:
        budget = RenderBudget(total=DEFAULT_RENDER_BUDGET_UNITS)
        with spending_from(budget=budget):
            format_markdown(markdown=FormattedMarkdownTestData.NOTES)
        assert budget.remaining < DEFAULT_RENDER_BUDGET_UNITS - len(FormattedMarkdownTestData.NOTES)

    def test_inside_a_render_an_overdraft_is_the_render_s_own_template_error(self) -> None:
        # A budget that affords the text alone, not the conversion: the refusal is the render's, which a template fill
        # catches with every other template error.
        budget = RenderBudget(total=len(FormattedMarkdownTestData.NOTES) * 4)
        with spending_from(budget=budget), pytest.raises(RenderBudgetExceededError, match="formatting Markdown") as caught:
            format_markdown(markdown=FormattedMarkdownTestData.NOTES)
        assert isinstance(caught.value, TemplateError)
        assert not isinstance(caught.value, MarkdownFormattingBudgetError)
