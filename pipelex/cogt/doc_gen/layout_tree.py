"""The layout tree: what the auto-layout of a step's inputs is, before any engine writes it.

A `PipeDocGen` step with no template lays its inputs out by itself, and every format's engine writes the
same tree: the built-in PDF engine on ReportLab, and the Excel and Word engines of the Pipelex document
generation plugin. The tree is plain data, so it crosses a process boundary as JSON and it is part of
the engines' contract (`render_job.py`):

- the scalar fields of a structure make a **field grid**, labelled from the field titles;
- a list of flat structures makes a **table**;
- a nested structure makes a **section**, with its own blocks;
- a `Text` makes **paragraphs**, a `Markdown` a **markdown** block for the engine to format, and an
  image an **image** block, which the engine reads through `RenderResources`.

`layout_builder.py` builds it from stuff contents.
"""

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

LayoutScalar = str | bool | int | float | datetime.datetime | datetime.date | datetime.time | None


class LayoutField(BaseModel):
    label: str
    value: LayoutScalar


class LayoutColumn(BaseModel):
    key: str
    label: str


class FieldGridBlock(BaseModel):
    kind: Literal["field_grid"] = "field_grid"
    fields: list[LayoutField]


class TableBlock(BaseModel):
    kind: Literal["table"] = "table"
    title: str
    path: str = Field(description="The dotted path of the list this table shows, such as 'invoice.line_items'")
    columns: list[LayoutColumn]
    rows: list[dict[str, LayoutScalar]]


class ParagraphsBlock(BaseModel):
    kind: Literal["paragraphs"] = "paragraphs"
    paragraphs: list[str]


class MarkdownBlock(BaseModel):
    """Markdown source, which the engine formats: headings, emphasis, lists, tables, code and links."""

    kind: Literal["markdown"] = "markdown"
    markdown: str


class ImageBlock(BaseModel):
    kind: Literal["image"] = "image"
    url: str
    caption: str | None = None


class SectionBlock(BaseModel):
    kind: Literal["section"] = "section"
    title: str
    level: int
    blocks: list["LayoutBlock"]


LayoutBlock = Annotated[
    FieldGridBlock | TableBlock | ParagraphsBlock | MarkdownBlock | ImageBlock | SectionBlock,
    Field(discriminator="kind"),
]


class LayoutDocument(BaseModel):
    title: str
    blocks: list[LayoutBlock]

    def image_urls(self) -> list[str]:
        """The URL of every image block, in document order: what an engine will read to print the tree."""
        urls: list[str] = []
        _collect_image_urls(blocks=self.blocks, urls=urls)
        return urls


def _collect_image_urls(*, blocks: list[LayoutBlock], urls: list[str]) -> None:
    for block in blocks:
        match block:
            case ImageBlock():
                urls.append(block.url)
            case SectionBlock():
                _collect_image_urls(blocks=block.blocks, urls=urls)
            case FieldGridBlock() | TableBlock() | ParagraphsBlock() | MarkdownBlock():
                pass


SectionBlock.model_rebuild()
