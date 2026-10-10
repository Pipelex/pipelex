"""The document engine contract's formatted Markdown, for an engine that prints Markdown in its own format.

An engine that fills a template of its own format, a Word document's tags or an Excel workbook's cells, prints a text
written in Markdown from `format_markdown`, rather than from markdown-it's syntax tree or a converter of its own, so
it reads Markdown by the rules the built-in PDF engine reads it by: CommonMark with tables and strikethrough, raw HTML
shown as text, only an `http`, `https` or `mailto` target kept as a link, and an image never fetched, printing
`[image: alt]`. The HTML conversion (`layout_display.markdown_as_html`) follows markdown-it's own rules instead, which
keep a link to any target but a `javascript:`, `vbscript:`, `file:` or non-image `data:` one and show an image as an
`<img>`.

The result, a `FormattedMarkdown`, is plain data: an ordered list of blocks, each holding the spans it prints and the
list and quote depths it sits at. The structure and the conversion live in `pipelex/tools/markdown/`
(`markdown_formatting.py`, by the rules of `markdown_rules.py`), where the plain-data templates' `markdown` filter
reads them too, and this module names them for an engine (`__all__`): an engine imports them from here, the contract,
and never from `tools`, which may move in an ordinary release.

Inside a template render, as the `markdown` filter of plain-data templates converts, the conversion is charged to the
render's budget the way the HTML conversion is (`markdown_parser.py`), and an overdraft is the render's own
`RenderBudgetExceededError`. Outside any render, as an engine converts from its own code, it spends from a budget of
its own, as large as one render's, and an overdraft raises `MarkdownFormattingBudgetError`.

This module is part of the document engine contract (`pipelex/plugins/contract.py`), and it imports no engine
library, so a plugin's engine can use it without loading ReportLab.
"""

from pipelex.cogt.doc_gen.exceptions import MarkdownFormattingBudgetError
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, RenderBudget, RenderBudgetExceededError, active_render_budget
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
    FormattedTableCell,
    FormattedTableRow,
    LineBreakSpan,
    TextSpan,
    format_markdown_within_budget,
    spans_text,
)
from pipelex.tools.markdown.markdown_rules import CellAlignment

__all__ = [
    "CellAlignment",
    "FormattedBlock",
    "FormattedCodeBlock",
    "FormattedHeading",
    "FormattedListItem",
    "FormattedMarkdown",
    "FormattedParagraph",
    "FormattedRule",
    "FormattedSpan",
    "FormattedTable",
    "FormattedTableCell",
    "FormattedTableRow",
    "LineBreakSpan",
    "TextSpan",
    "format_markdown",
    "spans_text",
]


def format_markdown(*, markdown: str) -> FormattedMarkdown:
    """A Markdown text as the blocks and spans an engine prints, read by the rules the built-in PDF engine reads it by.

    The conversion is charged before it parses, for every character of its source and every cell of its tables, and
    its result, bounded from the parsed tokens, must fit what is left before it is built. Inside a template render it
    spends from the render's budget; outside any, from a budget of its own, as large as one render's.

    Raises:
        RenderBudgetExceededError: inside a template render, the conversion would overdraw the render's budget.
        MarkdownFormattingBudgetError: outside any render, the conversion would spend more than the budget it gets
            of its own.
    """
    budget = active_render_budget()
    if budget is not None:
        return format_markdown_within_budget(markdown_text=markdown, budget=budget)
    own_budget = RenderBudget(total=DEFAULT_RENDER_BUDGET_UNITS)
    try:
        return format_markdown_within_budget(markdown_text=markdown, budget=own_budget)
    except RenderBudgetExceededError as exc:
        msg = (
            f"Formatting a Markdown text of {len(markdown):,} characters would spend more than the {own_budget.total:,} work units "
            "a conversion outside a template render may spend: its text, its tables or what they format into is too large."
        )
        raise MarkdownFormattingBudgetError(msg) from exc
