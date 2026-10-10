"""Markdown formatted into plain data, for a document engine that prints it in its own format rather than through HTML.

An engine that fills a template of its own format, a Word document's tags or an Excel workbook's cells, prints a text
written in Markdown from a `FormattedMarkdown`, rather than from markdown-it's syntax tree or a converter of its own,
so it reads Markdown by the rules the built-in PDF engine reads it by (`markdown_rules.py`). The structure is plain
data: an ordered list of blocks, each holding the spans it prints.

- **Blocks**: a paragraph, a heading with its level, a list item with its marker as printed and its first paragraph
  or heading, a code block's lines, a horizontal rule, and a table of rows of cells, its header row marked and each
  cell aligned as its column is. Every block has a list depth and a quote depth, the list items and the quotations
  it sits in, 0 outside any: a quoted paragraph is a paragraph one quotation deep, and a code block inside a list
  item is a code block one list deep.
- **Spans**: a text with its bold, italic, strikethrough and code flags and the address it links to, if any, or a line
  break.
- **Plain text**: `str()` of the result is its text, each block on lines of its own, indented under the list item it
  sits in, list markers kept and every other piece of markup gone, for a place that cannot show formatting; and the
  result is true when it holds a block, so a template's `{% if notes | markdown %}` is false for an empty or a blank
  text.

It parses with the one parser Pipelex reads Markdown with (`get_markdown_parser`), its inline nesting capped
(`markdown_syntax_tree`), and reads it by the rules the built-in PDF engine follows:

- CommonMark with tables and strikethrough, and raw HTML shown as text;
- a soft line break read as a space, and a hard one, two trailing spaces or a backslash, as a line break;
- bullets alternating a bullet and an en dash by depth, and an ordered list numbered from its own `start`;
- only an `http`, `https` or `mailto` target kept as a link, any other printing its text alone;
- an image never fetched, printing `[image: alt]` in italics;
- a node the converter does not know printing its text, and never failing the document.

The conversion spends from the budget it is given, charged as the HTML conversion is (`charged_parse`), and an
overdraft raises `RenderBudgetExceededError`. The document engine contract's `format_markdown`
(`pipelex/cogt/doc_gen/formatted_markdown.py`) gives it the active render's budget or one of its own.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Final, Literal

from markdown_it.tree import SyntaxTreeNode
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex.tools.jinja2.jinja2_render_budget import RenderBudget
from pipelex.tools.markdown.markdown_parser import charged_parse, markdown_syntax_tree
from pipelex.tools.markdown.markdown_rules import (
    CellAlignment,
    cell_alignment,
    code_text,
    heading_level,
    is_linked_href,
    list_bullet,
    list_start,
    plain_text,
)

if TYPE_CHECKING:
    from markdown_it.token import Token

_FORMATTING: Final = "formatting Markdown"

# What one part of the result takes at most besides its text, a span, a block, a row or a cell, with the syntax-tree
# node it is read from: a frozen pydantic model and its place in a list measure under six hundred bytes.
_PART_UNITS: Final = 1024

# The indentation of a block's text by list depth, in the plain text.
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


class _PlacedBlock(BaseModel):
    """Where a block sits: inside how many list items, and inside how many quotations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    list_depth: int = Field(default=0, ge=0, description="How many list items the block sits in: 0 outside any list")
    quote_depth: int = Field(default=0, ge=0, description="How many quotations the block sits in: 0 outside any quotation")


class FormattedParagraph(_PlacedBlock):
    """A paragraph: inside a list item, one after the paragraph or heading the item's marker prints with."""

    kind: Literal["paragraph"] = "paragraph"
    spans: list[FormattedSpan]


class FormattedHeading(_PlacedBlock):
    kind: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=6, description="From 1, the largest, to 6")
    spans: list[FormattedSpan]


class FormattedListItem(_PlacedBlock):
    """A list item's marker, with the paragraph or the heading it opens with; the rest of the item follows as blocks
    one list deeper than the list it sits in, with the item's `list_depth`.
    """

    kind: Literal["list_item"] = "list_item"
    list_depth: int = Field(default=1, ge=1, description="How many lists the item sits in, its own included: 1 for an item of a top-level list")
    marker: str = Field(description="The bullet or the number as printed, such as '•' or '3.'")
    heading_level: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="The level of the heading the item opens with, or None when it opens with a paragraph or with nothing to print beside its marker",
    )
    spans: list[FormattedSpan] = Field(
        description="The text printed beside the marker: empty when the item opens with a list, a code block or a table"
    )


class FormattedCodeBlock(_PlacedBlock):
    """A fenced or indented code block, its lines as written, tabs expanded to four spaces."""

    kind: Literal["code_block"] = "code_block"
    lines: list[str]


class FormattedRule(_PlacedBlock):
    kind: Literal["rule"] = "rule"


class FormattedTableCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spans: list[FormattedSpan]
    alignment: CellAlignment | None = Field(default=None, description="The alignment the column's delimiter row sets, or None when it sets none")


class FormattedTableRow(BaseModel):
    """A row of a table, every row holding as many cells as the header has columns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_header: bool
    cells: list[FormattedTableCell]


class FormattedTable(_PlacedBlock):
    kind: Literal["table"] = "table"
    rows: list[FormattedTableRow]


FormattedBlock = Annotated[
    FormattedParagraph | FormattedHeading | FormattedListItem | FormattedCodeBlock | FormattedRule | FormattedTable,
    Field(discriminator="kind"),
]


class FormattedMarkdown(BaseModel):
    """A Markdown text as its blocks, in order, for an engine to print in its own format.

    `str()` is its plain text, and it is true when it holds a block.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: list[FormattedBlock]

    @override
    def __str__(self) -> str:
        """The plain text: each block on lines of its own, indented two spaces for every list item it sits in, a list
        item's marker printed before its text, table cells separated by tabs, a code block's lines as written, a rule
        left out, and every other piece of markup, a quotation's included, gone.
        """
        lines: list[str] = []
        for block in self.blocks:
            indent = _PLAIN_INDENT * block.list_depth
            match block:
                case FormattedListItem():
                    first_prefix = f"{_PLAIN_INDENT * (block.list_depth - 1)}{block.marker} "
                    lines.extend(_indented_lines(text=spans_text(spans=block.spans), first_prefix=first_prefix, prefix=indent))
                case FormattedParagraph() | FormattedHeading():
                    lines.extend(_indented_lines(text=spans_text(spans=block.spans), first_prefix=indent, prefix=indent))
                case FormattedCodeBlock():
                    lines.extend(_indented_lines(text="\n".join(block.lines), first_prefix=indent, prefix=indent))
                case FormattedRule():
                    pass
                case FormattedTable():
                    rows = "\n".join("\t".join(spans_text(spans=cell.spans) for cell in row.cells) for row in block.rows)
                    lines.extend(_indented_lines(text=rows, first_prefix=indent, prefix=indent))
        return "\n".join(lines)

    def __bool__(self) -> bool:
        """Whether the text formats into anything: an empty or a blank text holds no block."""
        return bool(self.blocks)


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


def _indented_lines(*, text: str, first_prefix: str, prefix: str) -> list[str]:
    """The lines of a block's text, the first after `first_prefix` and every other after `prefix`, an empty one bare."""
    lines: list[str] = []
    for index, line in enumerate(text.split("\n")):
        line_prefix = first_prefix if index == 0 else prefix
        lines.append(f"{line_prefix}{line}" if line else line_prefix.rstrip())
    return lines


########################################################################################
# Formatting
########################################################################################


def format_markdown_within_budget(*, markdown_text: str, budget: RenderBudget) -> FormattedMarkdown:
    """A Markdown text as the blocks and spans an engine prints, spending from `budget`.

    The conversion is charged before it parses, for every character of its source and every cell of its tables, and
    its result, bounded from the parsed tokens, must fit what is left before it is built (`charged_parse`); what it
    built is charged after.

    Raises:
        RenderBudgetExceededError: the conversion would overdraw `budget`.
    """
    parsed = charged_parse(markdown_text=markdown_text, budget=budget, operation=_FORMATTING, output_bound=_formatted_size_bound)
    formatter = _MarkdownFormatter()
    formatter.blocks(nodes=markdown_syntax_tree(tokens=parsed.tokens).children, list_depth=0, quote_depth=0)
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

    def blocks(self, *, nodes: list[SyntaxTreeNode], list_depth: int, quote_depth: int) -> None:
        for node in nodes:
            self._block(node=node, list_depth=list_depth, quote_depth=quote_depth)

    def _emit(self, *, block: FormattedBlock, text_length: int) -> None:
        self.formatted.append(block)
        self.units += _PART_UNITS + text_length

    def _block(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int) -> None:
        match node.type:
            case "paragraph":
                self._paragraph(spans=self._spans(nodes=node.children), list_depth=list_depth, quote_depth=quote_depth)
            case "heading":
                self._heading(node=node, list_depth=list_depth, quote_depth=quote_depth)
            case "bullet_list" | "ordered_list":
                self._list(node=node, list_depth=list_depth, quote_depth=quote_depth)
            case "table":
                self._table(node=node, list_depth=list_depth, quote_depth=quote_depth)
            case "fence" | "code_block":
                text = code_text(content=node.content)
                if text.strip():
                    code_block = FormattedCodeBlock(list_depth=list_depth, quote_depth=quote_depth, lines=text.split("\n"))
                    self._emit(block=code_block, text_length=len(text))
            case "blockquote":
                self.blocks(nodes=node.children, list_depth=list_depth, quote_depth=quote_depth + 1)
            case "hr":
                self._emit(block=FormattedRule(list_depth=list_depth, quote_depth=quote_depth), text_length=0)
            case _:
                text = plain_text(nodes=[node]).strip()
                if text:
                    self.units += _PART_UNITS
                    self._paragraph(spans=[TextSpan(text=text)], list_depth=list_depth, quote_depth=quote_depth)

    def _paragraph(self, *, spans: list[FormattedSpan], list_depth: int, quote_depth: int) -> None:
        paragraph = FormattedParagraph(list_depth=list_depth, quote_depth=quote_depth, spans=spans)
        self._emit(block=paragraph, text_length=_spans_length(spans=spans))

    def _heading(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int) -> None:
        spans = self._spans(nodes=node.children)
        heading = FormattedHeading(list_depth=list_depth, quote_depth=quote_depth, level=heading_level(tag=node.tag), spans=spans)
        self._emit(block=heading, text_length=_spans_length(spans=spans))

    def _list(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int) -> None:
        items = [child for child in node.children if child.type == "list_item"]
        is_ordered = node.type == "ordered_list"
        start = list_start(start=node.attrs.get("start")) if is_ordered else 1
        depth = list_depth + 1
        for index, item in enumerate(items):
            marker = f"{start + index}." if is_ordered else list_bullet(depth=depth)
            children = item.children
            # The marker prints on the line of the item's first paragraph or heading, or alone when the item opens with
            # anything else, such as a nested list, a code block or nothing.
            opening_spans: list[FormattedSpan] = []
            opening_level: int | None = None
            rest = children
            if children:
                first = children[0]
                match first.type:
                    case "paragraph":
                        opening_spans = self._spans(nodes=first.children)
                        rest = children[1:]
                    case "heading":
                        opening_spans = self._spans(nodes=first.children)
                        opening_level = heading_level(tag=first.tag)
                        rest = children[1:]
                    case _:
                        pass
            list_item = FormattedListItem(list_depth=depth, quote_depth=quote_depth, marker=marker, heading_level=opening_level, spans=opening_spans)
            self._emit(block=list_item, text_length=len(marker) + _spans_length(spans=opening_spans))
            self.blocks(nodes=rest, list_depth=depth, quote_depth=quote_depth)

    def _table(self, *, node: SyntaxTreeNode, list_depth: int, quote_depth: int) -> None:
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
                    cells.append(FormattedTableCell(spans=spans, alignment=cell_alignment(node=cell)))
                    self.units += _PART_UNITS
                if cells:
                    rows.append(FormattedTableRow(is_header=is_header, cells=cells))
                    self.units += _PART_UNITS
        if rows:
            self._emit(block=FormattedTable(list_depth=list_depth, quote_depth=quote_depth, rows=rows), text_length=text_length)

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
