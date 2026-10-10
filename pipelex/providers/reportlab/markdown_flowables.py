"""Markdown as ReportLab flowables, for the built-in PDF engine.

The Markdown is parsed by the one parser Pipelex formats Markdown with (`get_markdown_parser`), so a PDF reads it
as the `markdown` filter of HTML templates parses it, and the converter walks markdown-it's syntax tree rather than
its flat token stream, so a nested list lives inside its item and each list numbers its own items. The tree is built
with its inline nesting capped (`markdown_syntax_tree`), so emphasis nested hundreds deep prints its text rather than
overflowing the stack. The rules it shares with the formatting the engines of the other formats print from, the link
rule, the bullets by depth, a list's start, a heading's level, a code block's text, a table cell's alignment and the
plain text of nodes, are in `pipelex/tools/markdown/markdown_rules.py`.

What it prints:

- headings 1 to 6, paragraphs with bold, italics, strikethrough, inline code and links, soft breaks as spaces and
  hard breaks as line breaks;
- bullet and ordered lists, nested, an ordered list starting at its own `start`;
- tables, whose header row repeats on every page, with the column alignments the Markdown sets;
- fenced and indented code blocks in the monospace face, printed as written, long lines wrapped;
- blockquotes, indented behind a rule, and horizontal rules.

Every text is escaped into ReportLab's paragraph markup (`escape_text`), and only `http`, `https` and `mailto` links
become links: any other target prints its text alone. A Markdown image is never fetched: its alt text prints in
italics, as `[image: alt]`. A node the converter does not know prints its text, and never fails the document.
"""

from markdown_it.tree import SyntaxTreeNode
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.platypus import Flowable, HRFlowable, ListFlowable, Paragraph, Preformatted, Spacer  # type: ignore[import-untyped]

from pipelex.providers.reportlab.pdf_elements import (
    BOX_PADDING,
    LINK_COLOR_HEX,
    MONO_FONT,
    RULE_COLOR,
    SANS_FONT,
    TEXT_COLOR,
    ColumnExtent,
    PdfStyles,
    TableCell,
    boxed,
    data_table,
    escape_attribute,
    escape_text,
    fit_column_widths,
    heading_break,
    measure_column,
)
from pipelex.tools.markdown.markdown_parser import get_markdown_parser, markdown_syntax_tree
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

_MINIMUM_LIST_INDENT = 14.0
_BULLET_GAP = 6.0
_QUOTE_INDENT = 2 * BOX_PADDING
_MINIMUM_CODE_LINE_LENGTH = 20


def markdown_to_flowables(*, markdown_text: str, styles: PdfStyles, available_width: float) -> list[Flowable]:
    """The flowables that print a Markdown text in a frame `available_width` points wide."""
    tree = markdown_syntax_tree(tokens=get_markdown_parser().parse(markdown_text))
    return markdown_nodes_to_flowables(nodes=tree.children, styles=styles, available_width=available_width)


def markdown_nodes_to_flowables(*, nodes: list[SyntaxTreeNode], styles: PdfStyles, available_width: float) -> list[Flowable]:
    """The flowables that print the top-level block nodes of a parsed Markdown text."""
    return _MarkdownWriter(styles=styles).blocks(nodes=nodes, available_width=available_width, list_depth=0, is_contained=False)


class _MarkdownWriter:
    def __init__(self, *, styles: PdfStyles):
        self._styles = styles

    def blocks(self, *, nodes: list[SyntaxTreeNode], available_width: float, list_depth: int, is_contained: bool) -> list[Flowable]:
        flowables: list[Flowable] = []
        for node in nodes:
            flowables.extend(self._block(node=node, available_width=available_width, list_depth=list_depth, is_contained=is_contained))
        return flowables

    def _block(self, *, node: SyntaxTreeNode, available_width: float, list_depth: int, is_contained: bool) -> list[Flowable]:
        """The flowables of one block node; `is_contained` when it sits inside a list item or a quotation, where no page break can go."""
        match node.type:
            case "paragraph":
                style = self._styles.list_body if list_depth else self._styles.body
                return [Paragraph(inline_markup(nodes=node.children), style)]
            case "heading":
                heading = Paragraph(inline_markup(nodes=node.children), self._styles.heading(level=heading_level(tag=node.tag)))
                if is_contained:
                    return [heading]
                return [heading_break(), heading]
            case "bullet_list" | "ordered_list":
                return self._list(node=node, available_width=available_width, list_depth=list_depth)
            case "table":
                return self._table(node=node, available_width=available_width)
            case "fence" | "code_block":
                return self._code(text=node.content, available_width=available_width)
            case "blockquote":
                inner = self.blocks(nodes=node.children, available_width=available_width - _QUOTE_INDENT, list_depth=list_depth, is_contained=True)
                if not inner:
                    return []
                return [boxed(flowables=inner, width=available_width, is_code=False)]
            case "hr":
                return [HRFlowable(width="100%", thickness=0.6, color=RULE_COLOR, spaceBefore=4, spaceAfter=8)]
            case _:
                text = plain_text(nodes=[node]).strip()
                if not text:
                    return []
                return [Paragraph(escape_text(text=text), self._styles.body)]

    def _list(self, *, node: SyntaxTreeNode, available_width: float, list_depth: int) -> list[Flowable]:
        items = [child for child in node.children if child.type == "list_item"]
        if not items:
            return []
        is_ordered = node.type == "ordered_list"
        start = list_start(start=node.attrs.get("start")) if is_ordered else 1
        # Both bullets are in the bundled sans face.
        bullet = list_bullet(depth=list_depth + 1)
        labels = [f"{start + index}." for index in range(len(items))] if is_ordered else [bullet]
        font_size = self._styles.body.fontSize
        label_width = max(pdfmetrics.stringWidth(label, SANS_FONT, font_size) for label in labels)
        indent = max(label_width + _BULLET_GAP, _MINIMUM_LIST_INDENT)
        # Each item is the list of its own flowables: ReportLab bullets the first and numbers the items from `start`,
        # so a nested list, which sits inside its item, neither takes a number nor shifts the outer numbering.
        list_items: list[list[Flowable]] = []
        for item in items:
            content = self.blocks(nodes=item.children, available_width=available_width - indent, list_depth=list_depth + 1, is_contained=True)
            list_items.append(content or [Spacer(1, self._styles.list_body.leading)])
        list_flowable = ListFlowable(
            list_items,
            bulletType="1" if is_ordered else "bullet",
            start=start if is_ordered else bullet,
            bulletFormat="%s." if is_ordered else None,
            leftIndent=indent,
            bulletFontName=SANS_FONT,
            bulletFontSize=font_size,
            bulletColor=TEXT_COLOR,
            spaceAfter=3,
        )
        return [list_flowable]

    def _table(self, *, node: SyntaxTreeNode, available_width: float) -> list[Flowable]:
        header_rows: list[list[SyntaxTreeNode]] = []
        body_rows: list[list[SyntaxTreeNode]] = []
        for section in node.children:
            rows = header_rows if section.type == "thead" else body_rows
            rows.extend([cell for cell in row.children if cell.type in {"th", "td"}] for row in section.children if row.type == "tr")
        all_rows = header_rows[:1] + body_rows
        column_count = max((len(row) for row in all_rows), default=0)
        if column_count == 0:
            return []
        header_row = header_rows[0] if header_rows else None
        extents: list[ColumnExtent] = []
        for column_index in range(column_count):
            header_text = plain_text(nodes=[header_row[column_index]]) if header_row and column_index < len(header_row) else None
            cell_texts = (plain_text(nodes=[row[column_index]]) for row in body_rows if column_index < len(row))
            extents.append(measure_column(header=header_text, cells=cell_texts, available_width=available_width, column_count=column_count))
        col_widths = fit_column_widths(extents=extents, available_width=available_width)
        table_rows: list[list[TableCell]] = []
        for row_index, row in enumerate(all_rows):
            is_header = header_row is not None and row_index == 0
            cells: list[TableCell] = []
            for column_index in range(column_count):
                if column_index < len(row):
                    cell = row[column_index]
                    style = self._cell_style(alignment=cell_alignment(node=cell), is_header=is_header)
                    cells.append(Paragraph(inline_markup(nodes=cell.children), style))
                else:
                    cells.append("")
            table_rows.append(cells)
        return [data_table(rows=table_rows, col_widths=col_widths, has_header=header_row is not None, right_aligned_columns=[])]

    def _cell_style(self, *, alignment: CellAlignment | None, is_header: bool) -> ParagraphStyle:
        match alignment:
            case "right":
                return self._styles.cell_header_right if is_header else self._styles.cell_right
            case "center":
                return self._styles.cell_header_center if is_header else self._styles.cell_center
            case "left" | None:
                return self._styles.cell_header if is_header else self._styles.cell

    def _code(self, *, text: str, available_width: float) -> list[Flowable]:
        code = code_text(content=text)
        if not code.strip():
            return []
        code_style = self._styles.code
        character_width = pdfmetrics.stringWidth("0", MONO_FONT, code_style.fontSize)
        line_length = max(int((available_width - 2 * BOX_PADDING) // character_width), _MINIMUM_CODE_LINE_LENGTH)
        preformatted = Preformatted(code, code_style, maxLineLength=line_length, newLineChars="")
        return [boxed(flowables=[preformatted], width=available_width, is_code=True)]


def inline_markup(*, nodes: list[SyntaxTreeNode]) -> str:
    """Inline Markdown as ReportLab paragraph markup: every text escaped, emphasis, code and safe links as tags."""
    parts: list[str] = []
    for node in nodes:
        match node.type:
            case "text":
                parts.append(escape_text(text=node.content))
            case "softbreak":
                parts.append(" ")
            case "hardbreak":
                parts.append("<br/>")
            case "strong":
                parts.append(f"<b>{inline_markup(nodes=node.children)}</b>")
            case "em":
                parts.append(f"<i>{inline_markup(nodes=node.children)}</i>")
            case "s":
                parts.append(f"<strike>{inline_markup(nodes=node.children)}</strike>")
            case "code_inline":
                parts.append(f'<font face="{MONO_FONT}">{escape_text(text=node.content)}</font>')
            case "link":
                parts.append(_link_markup(node=node))
            case "image":
                alt_text = plain_text(nodes=node.children).strip() or node.content
                parts.append(f"<i>[image: {escape_text(text=alt_text)}]</i>")
            case _:
                if node.children:
                    parts.append(inline_markup(nodes=node.children))
                else:
                    parts.append(escape_text(text=node.content))
    return "".join(parts)


def _link_markup(*, node: SyntaxTreeNode) -> str:
    label = inline_markup(nodes=node.children)
    href = node.attrs.get("href")
    if not isinstance(href, str) or not is_linked_href(href=href):
        return label
    return f'<a href="{escape_attribute(value=href)}" color="{LINK_COLOR_HEX}">{label}</a>'
