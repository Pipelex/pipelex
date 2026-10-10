"""Markdown formatted for a document engine: the structure every engine prints a Markdown text from.

An engine that fills a template of its own format, a Word document's tags or an Excel workbook's cells, prints a text
written in Markdown from `format_markdown`, rather than from markdown-it's syntax tree or a converter of its own, so a
Markdown text reads the same in every format. The result, a `FormattedMarkdown`, is plain data: an ordered list of
blocks, each holding the spans it prints.

- **Blocks**: a paragraph, a heading with its level, a list item with its depth and its marker as printed, a code
  block's lines, a quotation with its depth, a horizontal rule, and a table of rows of cells, its header row marked.
- **Spans**: a text with its bold, italic, strikethrough and code flags and the address it links to, if any, or a line
  break.
- **Plain text**: `str()` of the result is its text, each block on a line of its own and list markers kept, every
  other piece of markup gone, for a place that cannot show formatting.

It parses with the one parser Pipelex reads Markdown with (`get_markdown_parser`), and follows the rules the built-in
PDF engine follows (`pipelex/providers/reportlab/markdown_flowables.py`), which shares its helpers with it from here:

- CommonMark with tables and strikethrough, and raw HTML shown as text;
- a soft line break read as a space, and a hard one, two trailing spaces or a backslash, as a line break;
- bullets alternating a bullet and an en dash by depth, and an ordered list numbered from its own `start`;
- only an `http`, `https` or `mailto` target kept as a link, any other printing its text alone;
- an image never fetched, printing `[image: alt]` in italics;
- a node the converter does not know printing its text, and never failing the document.

Inside a template render, as the `markdown` filter of plain-data templates converts, the conversion is charged to the
render's budget the way the HTML conversion is (`markdown_parser.py`), and an overdraft is the render's own
`RenderBudgetExceededError`. Outside any render, as an engine converts from its own code, it spends from a budget of
its own, as large as one render's, and an overdraft raises `MarkdownFormattingBudgetError`.

This module is part of the document engine contract (`pipelex/plugins/contract.py`), and it imports no engine
library, so a plugin's engine can use it without loading ReportLab.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal
from urllib.parse import urlsplit

from markdown_it.tree import SyntaxTreeNode
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex.cogt.doc_gen.exceptions import MarkdownFormattingBudgetError
from pipelex.tools.jinja2.jinja2_render_budget import (
    DEFAULT_RENDER_BUDGET_UNITS,
    MARKDOWN_UNITS_PER_CHARACTER,
    RenderBudget,
    RenderBudgetExceededError,
    active_render_budget,
)
from pipelex.tools.markdown.markdown_parser import get_markdown_parser, table_cells_bound

if TYPE_CHECKING:
    from markdown_it.token import Token

LINKED_SCHEMES: Final = frozenset({"http", "https", "mailto"})

# The bullets of nested bullet lists, by depth, alternating: a bullet and an en dash.
_BULLETS: Final = ("•", "–")

_FORMATTING: Final = "formatting Markdown"

# What one part of the result takes at most besides its text, a span, a block, a row or a cell, with the syntax-tree
# node it is read from: a frozen pydantic model and its place in a list measure under six hundred bytes.
_PART_UNITS: Final = 1024

# The indentation of a list item's text by depth, in the plain text.
_PLAIN_INDENT: Final = "  "


########################################################################################
# The structure
########################################################################################


class TextSpan(BaseModel):
    """A run of text, with the formatting the Markdown gives it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["text"] = "text"
    text: str
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    code: bool = Field(default=False, description="Inline code, which an engine prints in a monospace font")
    link: str | None = Field(default=None, description="The address the text links to: only an http, https or mailto one is kept")


class LineBreakSpan(BaseModel):
    """A hard line break inside a block: two trailing spaces or a backslash at the end of a line."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["line_break"] = "line_break"


FormattedSpan = Annotated[TextSpan | LineBreakSpan, Field(discriminator="kind")]


class FormattedParagraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["paragraph"] = "paragraph"
    spans: list[FormattedSpan]


class FormattedHeading(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["heading"] = "heading"
    level: int = Field(description="From 1, the largest, to 6")
    spans: list[FormattedSpan]


class FormattedListItem(BaseModel):
    """A paragraph of a list item: the item's first, with its marker, or a later one, which prints at its indent without one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["list_item"] = "list_item"
    depth: int = Field(description="How many lists the item sits in: 1 for an item of a top-level list")
    marker: str | None = Field(description="The bullet or the number as printed, such as '•' or '3.', or None for a later paragraph of the item")
    spans: list[FormattedSpan]


class FormattedCodeBlock(BaseModel):
    """A fenced or indented code block, its lines as written, tabs expanded to four spaces."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["code_block"] = "code_block"
    lines: list[str]


class FormattedQuotation(BaseModel):
    """A paragraph or a heading of a quotation; a list, a code block, a table or a rule inside one keeps its own kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["quotation"] = "quotation"
    depth: int = Field(description="How many quotations it sits in: 1 for a quotation in the text itself")
    spans: list[FormattedSpan]


class FormattedRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["rule"] = "rule"


class FormattedTableCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spans: list[FormattedSpan]


class FormattedTableRow(BaseModel):
    """A row of a table, every row holding as many cells as the header has columns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_header: bool
    cells: list[FormattedTableCell]


class FormattedTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["table"] = "table"
    rows: list[FormattedTableRow]


FormattedBlock = Annotated[
    FormattedParagraph | FormattedHeading | FormattedListItem | FormattedCodeBlock | FormattedQuotation | FormattedRule | FormattedTable,
    Field(discriminator="kind"),
]


class FormattedMarkdown(BaseModel):
    """A Markdown text as its blocks, in order, for an engine to print in its own format. `str()` is its plain text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: list[FormattedBlock]

    @override
    def __str__(self) -> str:
        """The plain text: each block on a line of its own, list items indented by depth with their markers, table cells
        separated by tabs, a code block's lines as written, a rule left out, and every other piece of markup gone.
        """
        lines: list[str] = []
        for block in self.blocks:
            match block:
                case FormattedParagraph() | FormattedHeading() | FormattedQuotation():
                    lines.append(spans_text(spans=block.spans))
                case FormattedListItem():
                    indent = _PLAIN_INDENT * (block.depth - 1)
                    text = spans_text(spans=block.spans)
                    if block.marker is None:
                        lines.append(f"{indent}{_PLAIN_INDENT}{text}")
                    else:
                        lines.append(f"{indent}{block.marker} {text}".rstrip())
                case FormattedCodeBlock():
                    lines.extend(block.lines)
                case FormattedRule():
                    pass
                case FormattedTable():
                    lines.extend("\t".join(spans_text(spans=cell.spans) for cell in row.cells) for row in block.rows)
        return "\n".join(lines)


def spans_text(*, spans: Sequence[FormattedSpan]) -> str:
    """The text of spans without their formatting, a line break as a line feed."""
    parts: list[str] = []
    for span in spans:
        match span:
            case TextSpan():
                parts.append(span.text)
            case LineBreakSpan():
                parts.append("\n")
    return "".join(parts)


########################################################################################
# Formatting
########################################################################################


def format_markdown(*, markdown: str) -> FormattedMarkdown:
    """A Markdown text as the blocks and spans an engine prints, read by the rules every engine reads Markdown by.

    The conversion is charged before it parses, for every character of its source and every cell of its tables, and
    its result, bounded from the parsed tokens, must fit what is left before it is built.

    Raises:
        RenderBudgetExceededError: inside a template render, the conversion would overdraw the render's budget.
        MarkdownFormattingBudgetError: outside any render, the conversion would spend more than the budget it gets
            of its own, as large as one render's.
    """
    budget = active_render_budget()
    if budget is not None:
        return _format_within(markdown=markdown, budget=budget)
    own_budget = RenderBudget(total=DEFAULT_RENDER_BUDGET_UNITS)
    try:
        return _format_within(markdown=markdown, budget=own_budget)
    except RenderBudgetExceededError as exc:
        msg = (
            f"Formatting a Markdown text of {len(markdown):,} characters would spend more than the {own_budget.total:,} work units "
            "a conversion outside a template render may spend: its text, its tables or what they format into is too large."
        )
        raise MarkdownFormattingBudgetError(msg) from exc


def _format_within(*, markdown: str, budget: RenderBudget) -> FormattedMarkdown:
    # The length first: the table scan reads every line, so it runs only once the source is affordable.
    budget.charge(units=MARKDOWN_UNITS_PER_CHARACTER * len(markdown), operation=_FORMATTING)
    budget.charge(units=MARKDOWN_UNITS_PER_CHARACTER * table_cells_bound(markdown_text=markdown), operation=_FORMATTING)
    env: dict[str, Any] = {}
    tokens = get_markdown_parser().parse(markdown, env)
    budget.afford(units=_formatted_size_bound(tokens=tokens), operation=_FORMATTING)
    formatter = _MarkdownFormatter()
    formatter.blocks(nodes=SyntaxTreeNode(tokens).children, list_depth=0, quote_depth=0, container=_Container.TEXT)
    budget.charge(units=formatter.units, operation=_FORMATTING)
    return FormattedMarkdown(blocks=formatter.formatted)


def _formatted_size_bound(*, tokens: Sequence["Token"]) -> int:
    """At most what the result made of `tokens` takes: a part for every token that opens or stands alone, with its text.

    A token holds a reference link's destination as it prints it, so a reference used ten thousand times counts ten
    thousand times, as an engine that prints a link's address beside its text prints it.
    """
    total = 0
    pending: list[Sequence[Token]] = [tokens]
    while pending:
        for token in pending.pop():
            if token.nesting < 0:
                continue
            total += _PART_UNITS
            if token.type != "inline":
                total += len(token.content)
            href = token.attrGet("href")
            if isinstance(href, str):
                total += len(href)
            if token.children:
                pending.append(token.children)
    return total


class _Container(StrEnum):
    """The innermost container a block sits in, which decides what a paragraph inside it becomes."""

    TEXT = "text"
    LIST_ITEM = "list_item"
    QUOTATION = "quotation"


class _SpanStyle(BaseModel):
    model_config = ConfigDict(frozen=True)

    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    code: bool = False
    link: str | None = None


class _SpanBuilder:
    """Spans as an inline walk emits them, adjacent texts of the same style joined into one span."""

    def __init__(self) -> None:
        self.spans: list[FormattedSpan] = []
        self._pending_texts: list[str] = []
        self._pending_style: _SpanStyle | None = None

    def text(self, *, text: str, style: _SpanStyle) -> None:
        if not text:
            return
        if style != self._pending_style:
            self._flush()
            self._pending_style = style
        self._pending_texts.append(text)

    def line_break(self) -> None:
        self._flush()
        self.spans.append(LineBreakSpan())

    def finish(self) -> list[FormattedSpan]:
        self._flush()
        return self.spans

    def _flush(self) -> None:
        style = self._pending_style
        if style is not None and self._pending_texts:
            self.spans.append(
                TextSpan(
                    text="".join(self._pending_texts),
                    bold=style.bold,
                    italic=style.italic,
                    strikethrough=style.strikethrough,
                    code=style.code,
                    link=style.link,
                )
            )
        self._pending_texts = []
        self._pending_style = None


class _MarkdownFormatter:
    """The walk of markdown-it's syntax tree into blocks, tallying the units of what it builds."""

    def __init__(self) -> None:
        self.formatted: list[FormattedBlock] = []
        self.units = 0

    def blocks(self, *, nodes: list[SyntaxTreeNode], list_depth: int, quote_depth: int, container: _Container) -> None:
        for node in nodes:
            self._block(node=node, list_depth=list_depth, quote_depth=quote_depth, container=container)

    def _emit(self, *, block: FormattedBlock, text_length: int) -> None:
        self.formatted.append(block)
        self.units += _PART_UNITS + text_length

    def _block(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int, container: _Container) -> None:
        match node.type:
            case "paragraph":
                self._text_block(spans=self._spans(nodes=node.children), list_depth=list_depth, quote_depth=quote_depth, container=container)
            case "heading":
                spans = self._spans(nodes=node.children)
                heading: FormattedBlock
                match container:
                    case _Container.QUOTATION:
                        heading = FormattedQuotation(depth=quote_depth, spans=spans)
                    case _Container.TEXT | _Container.LIST_ITEM:
                        heading = FormattedHeading(level=heading_level(tag=node.tag), spans=spans)
                self._emit(block=heading, text_length=_spans_length(spans=spans))
            case "bullet_list" | "ordered_list":
                self._list(node=node, list_depth=list_depth, quote_depth=quote_depth)
            case "table":
                self._table(node=node)
            case "fence" | "code_block":
                text = code_text(content=node.content)
                if text.strip():
                    self._emit(block=FormattedCodeBlock(lines=text.split("\n")), text_length=len(text))
            case "blockquote":
                self.blocks(nodes=node.children, list_depth=list_depth, quote_depth=quote_depth + 1, container=_Container.QUOTATION)
            case "hr":
                self._emit(block=FormattedRule(), text_length=0)
            case _:
                text = plain_text(nodes=[node]).strip()
                if text:
                    self._text_block(spans=[TextSpan(text=text)], list_depth=list_depth, quote_depth=quote_depth, container=container)

    def _text_block(self, *, spans: list[FormattedSpan], list_depth: int, quote_depth: int, container: _Container) -> None:
        """A paragraph, or what prints as one, as the container it sits in has it: a later paragraph of a list item, a
        quotation's paragraph, or a paragraph of the text.
        """
        block: FormattedBlock
        match container:
            case _Container.LIST_ITEM:
                block = FormattedListItem(depth=list_depth, marker=None, spans=spans)
            case _Container.QUOTATION:
                block = FormattedQuotation(depth=quote_depth, spans=spans)
            case _Container.TEXT:
                block = FormattedParagraph(spans=spans)
        self._emit(block=block, text_length=_spans_length(spans=spans))

    def _list(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int) -> None:
        items = [child for child in node.children if child.type == "list_item"]
        is_ordered = node.type == "ordered_list"
        start = list_start(start=node.attrs.get("start")) if is_ordered else 1
        depth = list_depth + 1
        for index, item in enumerate(items):
            marker = f"{start + index}." if is_ordered else list_bullet(depth=depth)
            children = item.children
            # The item's marker prints with its first paragraph, or alone when it opens with anything else, such as a
            # nested list, a code block or nothing.
            rest = children
            spans: list[FormattedSpan] = []
            if children and children[0].type == "paragraph":
                spans = self._spans(nodes=children[0].children)
                rest = children[1:]
            self._emit(block=FormattedListItem(depth=depth, marker=marker, spans=spans), text_length=len(marker) + _spans_length(spans=spans))
            self.blocks(nodes=rest, list_depth=depth, quote_depth=quote_depth, container=_Container.LIST_ITEM)

    def _table(self, *, node: SyntaxTreeNode) -> None:
        rows: list[FormattedTableRow] = []
        text_length = 0
        for section in node.children:
            is_header = section.type == "thead"
            for row in section.children:
                if row.type != "tr":
                    continue
                cells: list[FormattedTableCell] = []
                for cell in row.children:
                    if cell.type not in {"th", "td"}:
                        continue
                    spans = self._spans(nodes=cell.children)
                    text_length += _spans_length(spans=spans)
                    cells.append(FormattedTableCell(spans=spans))
                    self.units += _PART_UNITS
                if cells:
                    rows.append(FormattedTableRow(is_header=is_header, cells=cells))
                    self.units += _PART_UNITS
        if rows:
            self._emit(block=FormattedTable(rows=rows), text_length=text_length)

    def _spans(self, *, nodes: list[SyntaxTreeNode]) -> list[FormattedSpan]:
        builder = _SpanBuilder()
        self._inline(nodes=nodes, style=_SpanStyle(), builder=builder)
        spans = builder.finish()
        self.units += _PART_UNITS * len(spans)
        return spans

    def _inline(self, *, nodes: list[SyntaxTreeNode], style: _SpanStyle, builder: _SpanBuilder) -> None:
        for node in nodes:
            match node.type:
                case "text":
                    builder.text(text=node.content, style=style)
                case "softbreak":
                    builder.text(text=" ", style=style)
                case "hardbreak":
                    builder.line_break()
                case "strong":
                    self._inline(nodes=node.children, style=style.model_copy(update={"bold": True}), builder=builder)
                case "em":
                    self._inline(nodes=node.children, style=style.model_copy(update={"italic": True}), builder=builder)
                case "s":
                    self._inline(nodes=node.children, style=style.model_copy(update={"strikethrough": True}), builder=builder)
                case "code_inline":
                    builder.text(text=node.content, style=style.model_copy(update={"code": True}))
                case "link":
                    href = node.attrs.get("href")
                    link = href if isinstance(href, str) and is_linked_href(href=href) else None
                    self._inline(nodes=node.children, style=style.model_copy(update={"link": link}), builder=builder)
                case "image":
                    builder.text(text=plain_text(nodes=[node]), style=style.model_copy(update={"italic": True}))
                case _:
                    if node.children:
                        self._inline(nodes=node.children, style=style, builder=builder)
                    else:
                        builder.text(text=node.content, style=style)


def _spans_length(*, spans: Sequence[FormattedSpan]) -> int:
    """The characters spans hold: their texts, since every span of a link shares its one address."""
    total = 0
    for span in spans:
        match span:
            case TextSpan():
                total += len(span.text)
            case LineBreakSpan():
                total += 1
    return total


########################################################################################
# The rules the built-in PDF engine shares
########################################################################################


def is_linked_href(*, href: str) -> bool:
    """Whether a link target becomes a link in a document: only `http`, `https` and `mailto` do."""
    try:
        scheme = urlsplit(href.strip()).scheme
    except ValueError:
        return False
    return scheme.lower() in LINKED_SCHEMES


def list_bullet(*, depth: int) -> str:
    """The bullet of a bullet list `depth` lists deep, 1 for a top-level list: a bullet and an en dash, alternating."""
    return _BULLETS[(depth - 1) % len(_BULLETS)]


def list_start(*, start: str | float | None) -> int:
    """The number an ordered list starts at, from the `start` markdown-it reads off its first item: 1 when it has none."""
    if start is None:
        return 1
    try:
        return int(start)
    except (ValueError, OverflowError):
        return 1


def heading_level(*, tag: str) -> int:
    """A heading's level from its tag, `h1` to `h6`: 6 for any other tag."""
    if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
        return int(tag[1])
    return 6


def code_text(*, content: str) -> str:
    """A code block's text as it prints: as written, without its last line feed, tabs expanded to four spaces."""
    return content.rstrip("\n").expandtabs(4)


def plain_text(*, nodes: list[SyntaxTreeNode]) -> str:
    """The text of Markdown nodes without their markup, as it reads once printed, an image as `[image: alt]`."""
    parts: list[str] = []
    for node in nodes:
        match node.type:
            case "softbreak":
                parts.append(" ")
            case "hardbreak":
                parts.append("\n")
            case "image":
                parts.append(f"[image: {plain_text(nodes=node.children).strip() or node.content}]")
            case _:
                if node.children:
                    parts.append(plain_text(nodes=node.children))
                else:
                    parts.append(node.content)
    return "".join(parts)
