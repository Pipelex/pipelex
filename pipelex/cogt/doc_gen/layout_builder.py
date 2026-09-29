"""Build the layout tree of a step's inputs, the auto-layout every engine writes.

What counts as a table is decided by the CSV codec's own flatness gate, `flat_field_names`, so "a list
that makes a table" means the same thing everywhere in Pipelex. The builder deliberately does not reuse
`StructuredContent.rendered_html`, which renders a list of structures as a list of small two-column
tables, so an invoice's line items would never come out as one table.
"""

import datetime
from decimal import Decimal
from enum import Enum
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.doc_gen.layout_tree import (
    FieldGridBlock,
    ImageBlock,
    LayoutBlock,
    LayoutColumn,
    LayoutDocument,
    LayoutField,
    LayoutScalar,
    MarkdownBlock,
    ParagraphsBlock,
    SectionBlock,
    TableBlock,
)
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.tools.tabular.csv_codec import flat_field_names
from pipelex.tools.tabular.exceptions import CsvFlatnessError

# The tags after which the text of an HTML value starts a new paragraph when it is printed as text.
_HTML_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section", "article", "blockquote", "pre", "hr"}
)
# The tags whose content is never text a reader sees.
_HTML_HIDDEN_TAGS = frozenset({"script", "style", "head", "title", "template"})


class _HtmlTextExtractor(HTMLParser):
    """Collect an HTML value's visible text, one paragraph per block-level element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._paragraphs: list[str] = []
        self._current: list[str] = []
        self._hidden_depth = 0

    def _break(self) -> None:
        paragraph = " ".join("".join(self._current).split())
        if paragraph:
            self._paragraphs.append(paragraph)
        self._current = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HTML_HIDDEN_TAGS:
            self._hidden_depth += 1
        elif tag in _HTML_BLOCK_TAGS:
            self._break()

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in _HTML_HIDDEN_TAGS:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        elif tag in _HTML_BLOCK_TAGS:
            self._break()

    @override
    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self._current.append(data)

    def paragraphs(self) -> list[str]:
        self._break()
        return self._paragraphs


def html_to_paragraphs(html: str) -> list[str]:
    """The visible text of an HTML value, one paragraph per block-level element, with every tag removed.

    The built-in engine does not interpret HTML, so this is what an `Html` value prints as when a PDF is laid
    out without a template; a PDF that must keep the formatting uses an HTML template, which the plugin prints.
    """
    extractor = _HtmlTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.paragraphs()


def humanize(name: str) -> str:
    """`unit_price` reads 'Unit price', `lineItems` stays readable as 'LineItems'."""
    words = name.replace("_", " ").strip()
    if not words:
        return name
    return words[0].upper() + words[1:]


def _scalar(value: Any) -> tuple[bool, LayoutScalar]:
    """Whether a value is a scalar a field grid can hold, and the value as the grid holds it.

    A `Markdown` value is never a scalar: it is prose to format, so it gets a block of its own.
    """
    match value:
        case None | str() | bool() | int() | float() | datetime.datetime() | datetime.date() | datetime.time():
            return True, value
        case Decimal():
            return True, float(value)
        case Enum():
            return _scalar(value.value)
        case MarkdownContent():
            return False, None
        case TextContent():
            return True, value.text
        case NumberContent():
            return True, value.number
        case YesNoContent():
            return True, value.yes_no
        case DateContent():
            if value.time is None:
                return True, value.date
            return True, datetime.datetime.combine(value.date, value.time)
        case TimeContent():
            return True, value.time
        case _:
            return False, None


def _is_list_of_scalars(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(_scalar(item)[0] for item in value)  # pyright: ignore[reportUnknownVariableType]


def _joined_scalars(items: list[Any]) -> str:
    return ", ".join("" if (scalar := _scalar(item)[1]) is None else str(scalar) for item in items)


def _flat_columns(items: list[Any]) -> list[LayoutColumn] | None:
    """The table columns for a list of structures, or None when the list does not make a table.

    Only a structure a method declares makes a table. A native content such as an image or a Markdown text
    has flat fields too, but they are how it is stored rather than what it shows, so a list of them lays
    out item by item.
    """
    if not items:
        return None
    first_item: object = items[0]
    if not isinstance(first_item, StructuredContent):
        return None
    first_class = type(first_item)
    if not all(type(item) is first_class for item in items):
        return None
    try:
        field_names = flat_field_names(first_class)
    except CsvFlatnessError:
        return None
    columns: list[LayoutColumn] = []
    for field_name in field_names:
        field_info = first_class.model_fields[field_name]
        columns.append(LayoutColumn(key=field_name, label=field_info.title or humanize(field_name)))
    return columns


def _table(*, title: str, path: str, items: list[Any], columns: list[LayoutColumn]) -> TableBlock:
    rows: list[dict[str, LayoutScalar]] = []
    for item in items:
        row: dict[str, LayoutScalar] = {}
        for column in columns:
            _, cell = _scalar(getattr(item, column.key))
            row[column.key] = cell
        rows.append(row)
    return TableBlock(title=title, path=path, columns=columns, rows=rows)


def _paragraphs(text: str) -> ParagraphsBlock:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    return ParagraphsBlock(paragraphs=paragraphs)


def _blocks_for_value(*, value: Any, title: str, path: str, level: int) -> list[LayoutBlock]:
    """The blocks that show one value, which is either a whole input or a field inside one."""
    is_scalar, scalar = _scalar(value)
    if is_scalar and not isinstance(value, TextContent):
        return [FieldGridBlock(fields=[LayoutField(label=title, value=scalar)])]
    match value:
        case MarkdownContent():
            return [SectionBlock(title=title, level=level, blocks=[MarkdownBlock(markdown=value.text)])]
        case TextContent():
            return [SectionBlock(title=title, level=level, blocks=[_paragraphs(value.text)])]
        case HtmlContent():
            return [SectionBlock(title=title, level=level, blocks=[ParagraphsBlock(paragraphs=html_to_paragraphs(value.inner_html))])]
        case ImageContent():
            return [ImageBlock(url=value.url, caption=value.caption or title)]
        case DocumentContent():
            label = value.title or value.filename or title
            return [FieldGridBlock(fields=[LayoutField(label=label, value=value.public_url or value.url)])]
        case JSONContent():
            return _blocks_for_value(value=value.json_obj, title=title, path=path, level=level)
        case ListContent():
            return _blocks_for_list(items=list(value.items), title=title, path=path, level=level)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        case list():
            return _blocks_for_list(items=list(value), title=title, path=path, level=level)  # pyright: ignore[reportUnknownArgumentType]
        case BaseModel():
            return [SectionBlock(title=title, level=level, blocks=_blocks_for_structure(structure=value, path=path, level=level + 1))]
        case dict():
            fields: list[LayoutField] = []
            for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
                is_item_scalar, item_scalar = _scalar(item)
                fields.append(LayoutField(label=humanize(str(key)), value=item_scalar if is_item_scalar else str(item)))  # pyright: ignore[reportUnknownArgumentType]
            return [SectionBlock(title=title, level=level, blocks=[FieldGridBlock(fields=fields)])]
        case _:
            return [FieldGridBlock(fields=[LayoutField(label=title, value=str(value))])]


def _blocks_for_list(*, items: list[Any], title: str, path: str, level: int) -> list[LayoutBlock]:
    if _is_list_of_scalars(items):
        return [FieldGridBlock(fields=[LayoutField(label=title, value=_joined_scalars(items))])]
    columns = _flat_columns(items)
    if columns is not None:
        return [_table(title=title, path=path, items=items, columns=columns)]
    item_title = title[:-1] if title.endswith("s") and len(title) > 1 else title
    blocks: list[LayoutBlock] = []
    for index, item in enumerate(items, start=1):
        blocks.extend(_blocks_for_value(value=item, title=f"{item_title} {index}", path=f"{path}.{index - 1}", level=level + 1))
    return [SectionBlock(title=title, level=level, blocks=blocks)]


def _blocks_for_structure(*, structure: BaseModel, path: str, level: int) -> list[LayoutBlock]:
    """A structure lays out as one grid of its scalar fields, then its other fields in declared order."""
    grid_fields: list[LayoutField] = []
    other_blocks: list[LayoutBlock] = []
    for field_name, field_info in type(structure).model_fields.items():
        value = getattr(structure, field_name)
        label = field_info.title or humanize(field_name)
        field_path = f"{path}.{field_name}"
        is_scalar, scalar = _scalar(value)
        if is_scalar:
            grid_fields.append(LayoutField(label=label, value=scalar))
        elif _is_list_of_scalars(value):
            grid_fields.append(LayoutField(label=label, value=_joined_scalars(value)))
        else:
            other_blocks.extend(_blocks_for_value(value=value, title=label, path=field_path, level=level))
    blocks: list[LayoutBlock] = []
    if grid_fields:
        blocks.append(FieldGridBlock(fields=grid_fields))
    blocks.extend(other_blocks)
    return blocks


def _is_structure_input(content: StuffContent) -> bool:
    """Whether an input is a structure whose own fields can fill the document's top level."""
    if isinstance(content, (ListContent, TextContent, HtmlContent, ImageContent, DocumentContent, JSONContent)):
        return False
    is_scalar, _ = _scalar(content)
    return not is_scalar


def build_layout_document(*, title: str, named_contents: list[tuple[str, StuffContent]]) -> LayoutDocument:
    """Lay out a step's inputs as one document.

    A single input is the document itself: a structure's fields fill the top level, and a text, such as a
    `Markdown` report, is the whole body, under the given title in both cases. Several inputs each get a
    section of their own, in the order the step declares them.
    """
    if len(named_contents) == 1:
        name, content = named_contents[0]
        if _is_structure_input(content):
            return LayoutDocument(title=title, blocks=_blocks_for_structure(structure=content, path=name, level=1))
        single_blocks = _blocks_for_value(value=content, title=humanize(name), path=name, level=1)
        match single_blocks:
            case [SectionBlock(blocks=[MarkdownBlock() | ParagraphsBlock() as body_block])]:
                return LayoutDocument(title=title, blocks=[body_block])
            case _:
                return LayoutDocument(title=title, blocks=single_blocks)
    blocks: list[LayoutBlock] = []
    for name, content in named_contents:
        blocks.extend(_blocks_for_value(value=content, title=humanize(name), path=name, level=1))
    return LayoutDocument(title=title, blocks=blocks)
