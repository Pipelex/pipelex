"""The built-in PDF engine: it prints the layout tree of a `PipeDocGen` step with no template, on ReportLab.

It writes the tree as ReportLab flowables on A4 portrait pages:

- the document's title at the top, and the title of the render job in a running header on every page, with
  "Page N of M" in the footer, which is why the document is built twice, the first pass counting the pages;
- a field grid as a two-column table of bold labels and their values;
- a table block as a table whose header row repeats on every page, its cells wrapping, its columns fitted to the
  page, and its numeric columns aligned right;
- a section as a heading whose size follows its level, then its own blocks;
- paragraphs as they are, Markdown through its converter (`markdown_flowables`), and an image from the bytes the
  render's resources read, scaled to the page with its caption under it.

Every text is escaped before it enters ReportLab's paragraph markup, so a value prints as written. The engine
fetches nothing itself: an image is read through `RenderResources`, which applies the run's read scope, and a
Markdown image is not read at all. It registers its bundled fonts once per process (`pdf_elements`), and it keeps
nothing of one render into the next, so one instance serves every render of its process, from any thread.

Renders are built one at a time in a process (`_BUILD_LOCK`): ReportLab subsets a registered TrueType font through a
cursor the font keeps on its file, so two documents saved at once corrupt each other's fonts. That costs no
throughput, since a build is pure Python and would hold the interpreter lock anyway, and the images are read before
the lock is taken, so a slow image does not hold up another render.
"""

import datetime
import io
import threading
from typing import NamedTuple

from PIL import Image as PilImage
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer  # type: ignore[import-untyped]
from reportlab.platypus.doctemplate import LayoutError  # type: ignore[import-untyped]
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.cogt.doc_gen.layout_tree import (
    FieldGridBlock,
    ImageBlock,
    LayoutBlock,
    LayoutDocument,
    LayoutScalar,
    MarkdownBlock,
    ParagraphsBlock,
    SectionBlock,
    TableBlock,
)
from pipelex.cogt.doc_gen.render_job import DocumentRendererProtocol, RenderedDocument, RenderJob, RenderResources
from pipelex.providers.reportlab.markdown_flowables import markdown_to_flowables
from pipelex.providers.reportlab.pdf_elements import (
    MUTED_COLOR,
    RULE_COLOR,
    SANS_BOLD_FONT,
    SANS_FONT,
    PdfStyles,
    TableCell,
    build_pdf_styles,
    data_table,
    escape_text,
    field_grid_table,
    fit_column_widths,
    heading_break,
    measure_column,
    register_bundled_fonts,
    text_cell,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = RIGHT_MARGIN = 18 * mm
TOP_MARGIN = 22 * mm
BOTTOM_MARGIN = 20 * mm
FRAME_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
FRAME_HEIGHT = PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN

# An image is printed at 96 pixels to the inch unless that is wider than the frame or taller than this share of it.
_IMAGE_POINTS_PER_PIXEL = 72 / 96
_IMAGE_MAX_HEIGHT = FRAME_HEIGHT * 0.6
_IMAGE_SPACE_BEFORE = 6.0

# A field grid's label column takes the width of its widest label, up to this share of the frame.
_GRID_LABEL_MAX_SHARE = 0.4

_RUNNING_TEXT_FONT_SIZE = 8.0
_HEADER_BASELINE = PAGE_HEIGHT - 12 * mm
_FOOTER_BASELINE = 10 * mm

_PDF_CREATOR = "Pipelex"

_BUILD_LOCK = threading.Lock()


class ReportlabPdfRenderer(DocumentRendererProtocol):
    """The engine that prints a `pdf` from the layout tree: `DocGenFormat.PDF` from `DocGenSource.LAYOUT`.

    Built once per process by its plugin's factory, which is when it registers the bundled fonts and builds its
    styles; `render` keeps its state in objects of its own call, so concurrent renders do not meet.
    """

    def __init__(self) -> None:
        register_bundled_fonts()
        self._styles = build_pdf_styles()

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        """Print a render job's layout tree as a PDF.

        Raises:
            DocGenRenderError: the job is not a PDF from the layout, an image cannot be read as one, or something in
                the document cannot be laid out on an A4 page.
            UriReadRefusedError: the run's read scope does not allow an image the document names.
        """
        layout = _layout_of_pdf_job(job=job)
        images = _RenderImages(resources=resources)
        images.preload(layout=layout)
        with _BUILD_LOCK:
            first_pass = self._build(job=job, layout=layout, images=images, page_count=None)
            second_pass = self._build(job=job, layout=layout, images=images, page_count=first_pass.page_count)
        return RenderedDocument(data=second_pass.data)

    def _build(self, *, job: RenderJob, layout: LayoutDocument, images: "_RenderImages", page_count: int | None) -> "_BuiltPass":
        origins: dict[int, str] = {}
        story = _LayoutWriter(styles=self._styles, images=images, origins=origins).document(layout=layout)
        buffer = io.BytesIO()
        doc_template = _PagedDocTemplate(buffer=buffer, title=job.title, page_count=page_count, origins=origins)
        try:
            doc_template.build(story)
        except LayoutError as exc:
            where = doc_template.last_origin or "an element of the document"
            msg = (
                f"The PDF engine cannot print '{job.filename}': {where} does not fit on an A4 page, "
                "as part of it is taller than a page and cannot be split across pages."
            )
            raise DocGenRenderError(msg).as_caller_fault() from exc
        return _BuiltPass(data=buffer.getvalue(), page_count=doc_template.page)


def _layout_of_pdf_job(*, job: RenderJob) -> LayoutDocument:
    """The layout tree of a job this engine prints, which is a PDF from the layout: the registry routes no other here."""
    refusal = f"The built-in PDF engine prints a pdf from the auto-layout of its inputs, not a {job.format} {job.source.desc}."
    match job.format:
        case DocGenFormat.PDF:
            pass
        case DocGenFormat.XLSX | DocGenFormat.DOCX | DocGenFormat.PPTX:
            raise DocGenRenderError(refusal)
    match job.source:
        case DocGenSource.LAYOUT:
            pass
        case DocGenSource.HTML | DocGenSource.TEMPLATE_FILE:
            raise DocGenRenderError(refusal)
    if job.layout is None:
        raise DocGenRenderError(refusal)
    return job.layout


class _BuiltPass(NamedTuple):
    data: bytes
    page_count: int


class _LoadedImage(NamedTuple):
    url: str
    data: bytes
    width_px: int
    height_px: int


class _RenderImages:
    """The images of one render, each read once through the render's resources, and kept for both build passes.

    They are numbered in document order, the order `LayoutDocument.image_urls` and the writer both follow, and each
    read names its number as its position: "image 2 of the document".
    """

    def __init__(self, *, resources: RenderResources):
        self._resources = resources
        self._images: dict[int, _LoadedImage] = {}

    def preload(self, *, layout: LayoutDocument) -> None:
        """Read every image of the layout, before the build takes its lock."""
        for number, url in enumerate(layout.image_urls(), start=1):
            self.get(number=number, url=url)

    def get(self, *, number: int, url: str) -> _LoadedImage:
        loaded = self._images.get(number)
        if loaded is None or loaded.url != url:
            position = f"image {number} of the document"
            data = self._resources.load(uri=url, position=position)
            loaded = _decode_image(url=url, data=data, position=position)
            self._images[number] = loaded
        return loaded


def _decode_image(*, url: str, data: bytes, position: str) -> _LoadedImage:
    """Decode an image fully, so a file that is not an image, or a truncated one, fails here and names its position."""
    try:
        with PilImage.open(io.BytesIO(data)) as pil_image:
            pil_image.load()
            width_px, height_px = pil_image.size
    except (OSError, ValueError, SyntaxError, PilImage.DecompressionBombError) as exc:
        msg = f"The PDF engine cannot print {position}: its file is not an image it reads, such as PNG, JPEG, GIF or WebP."
        raise DocGenRenderError(msg).as_caller_fault() from exc
    if width_px <= 0 or height_px <= 0:
        msg = f"The PDF engine cannot print {position}: the image is empty."
        raise DocGenRenderError(msg).as_caller_fault()
    return _LoadedImage(url=url, data=data, width_px=width_px, height_px=height_px)


class _PagedDocTemplate(BaseDocTemplate):
    """An A4 document whose pages carry a running header and "Page N of M", and which remembers what it was laying out.

    `page_count` is None on the first pass, which is the pass that counts the pages. `origins` names, in the author's
    terms, the flowables the writer made, so a layout error can say which part of the document did not fit.
    """

    def __init__(self, *, buffer: io.BytesIO, title: str, page_count: int | None, origins: dict[int, str]):
        super().__init__(  # pyright: ignore[reportUnknownMemberType] - the stubs leave BaseDocTemplate.__init__ partly untyped
            buffer,
            pagesize=A4,
            leftMargin=LEFT_MARGIN,
            rightMargin=RIGHT_MARGIN,
            topMargin=TOP_MARGIN,
            bottomMargin=BOTTOM_MARGIN,
            title=title,
            creator=_PDF_CREATOR,
        )
        # One frame with no padding, so the frame is exactly `FRAME_WIDTH` wide, which the writers size tables to.
        body_frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN, FRAME_WIDTH, FRAME_HEIGHT, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body"
        )
        self.addPageTemplates([PageTemplate(id="page", frames=[body_frame])])
        self._running_title = title
        self._page_count = page_count
        self._origins = origins
        self.last_origin: str | None = None

    @override
    def handle_flowable(self, flowables: list[Flowable]) -> None:
        # The part of a table or a paragraph split over a page is a flowable the writer did not make, and it follows
        # the one it was split from: the last origin seen is still the right one.
        if flowables:
            origin = self._origins.get(id(flowables[0]))
            if origin is not None:
                self.last_origin = origin
        super().handle_flowable(flowables)

    @override
    def beforePage(self) -> None:
        # Drawn as the page begins, so the header and the page number come first in the page's text.
        canvas = self.canv
        canvas.saveState()
        canvas.setFont(SANS_FONT, _RUNNING_TEXT_FONT_SIZE)
        canvas.setFillColor(MUTED_COLOR)
        canvas.drawString(
            LEFT_MARGIN,
            _HEADER_BASELINE,
            _fit_line(text=self._running_title, font_name=SANS_FONT, font_size=_RUNNING_TEXT_FONT_SIZE, max_width=FRAME_WIDTH),
        )
        canvas.setStrokeColor(RULE_COLOR)
        canvas.setLineWidth(0.4)
        canvas.line(LEFT_MARGIN, _HEADER_BASELINE - 3, PAGE_WIDTH - RIGHT_MARGIN, _HEADER_BASELINE - 3)
        page_label = f"Page {self.page}" if self._page_count is None else f"Page {self.page} of {self._page_count}"
        canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, _FOOTER_BASELINE, page_label)
        canvas.restoreState()


def _fit_line(*, text: str, font_name: str, font_size: float, max_width: float) -> str:
    """A text on one line, cut with an ellipsis when it is wider than `max_width`."""
    line = " ".join(text.split())
    if pdfmetrics.stringWidth(line, font_name, font_size) <= max_width:
        return line
    ellipsis = "…"
    kept_length = 0
    too_long_length = len(line)
    while too_long_length - kept_length > 1:
        middle_length = (kept_length + too_long_length) // 2
        if pdfmetrics.stringWidth(line[:middle_length] + ellipsis, font_name, font_size) <= max_width:
            kept_length = middle_length
        else:
            too_long_length = middle_length
    return line[:kept_length].rstrip() + ellipsis


class _LayoutWriter:
    """Writes one layout tree as the flowables of one build pass."""

    def __init__(self, *, styles: PdfStyles, images: _RenderImages, origins: dict[int, str]):
        self._styles = styles
        self._images = images
        self._origins = origins
        self._image_count = 0

    def document(self, *, layout: LayoutDocument) -> list[Flowable]:
        story: list[Flowable] = [Paragraph(escape_text(text=layout.title), self._styles.title)]
        story.extend(self._blocks(blocks=layout.blocks, level=1, section_title=None))
        return story

    def _blocks(self, *, blocks: list[LayoutBlock], level: int, section_title: str | None) -> list[Flowable]:
        """The flowables of a list of blocks, `level` being the heading level of a titled block among them."""
        where = f"'{section_title}'" if section_title is not None else "the document"
        flowables: list[Flowable] = []
        for block in blocks:
            match block:
                case FieldGridBlock():
                    if block.fields:
                        flowables.append(self._tagged(flowable=self._field_grid(block=block), origin=f"the fields of {where}"))
                case TableBlock():
                    flowables.extend(self._heading(title=block.title, level=level))
                    flowables.extend(self._table(block=block))
                case ParagraphsBlock():
                    for paragraph in block.paragraphs:
                        flowables.append(
                            self._tagged(flowable=Paragraph(escape_text(text=paragraph), self._styles.body), origin=f"the text of {where}")
                        )
                case MarkdownBlock():
                    for flowable in markdown_to_flowables(markdown_text=block.markdown, styles=self._styles, available_width=FRAME_WIDTH):
                        flowables.append(self._tagged(flowable=flowable, origin=f"the Markdown of {where}"))
                case ImageBlock():
                    flowables.append(self._image(block=block))
                case SectionBlock():
                    flowables.extend(self._heading(title=block.title, level=block.level))
                    flowables.extend(self._blocks(blocks=block.blocks, level=block.level + 1, section_title=block.title))
        return flowables

    def _tagged(self, *, flowable: Flowable, origin: str) -> Flowable:
        self._origins[id(flowable)] = origin
        return flowable

    def _heading(self, *, title: str, level: int) -> list[Flowable]:
        return [heading_break(), Paragraph(escape_text(text=title), self._styles.heading(level=level))]

    def _field_grid(self, *, block: FieldGridBlock) -> Flowable:
        label_style = self._styles.grid_label
        widest_label = max(
            pdfmetrics.stringWidth(word, SANS_BOLD_FONT, label_style.fontSize)
            for field in block.fields
            for word in [field.label, *field.label.split()]
        )
        label_width = min(widest_label + 12, FRAME_WIDTH * _GRID_LABEL_MAX_SHARE)
        rows: list[list[Flowable]] = [
            [Paragraph(escape_text(text=field.label), label_style), Paragraph(escape_text(text=display_scalar(value=field.value)), self._styles.body)]
            for field in block.fields
        ]
        return field_grid_table(rows=rows, col_widths=[label_width, FRAME_WIDTH - label_width])

    def _table(self, *, block: TableBlock) -> list[Flowable]:
        if not block.columns:
            return []
        column_count = len(block.columns)
        displayed_rows = [[display_scalar(value=row.get(column.key)) for column in block.columns] for row in block.rows]
        extents = [
            measure_column(
                header=column.label,
                cells=(displayed_row[index] for displayed_row in displayed_rows),
                available_width=FRAME_WIDTH,
                column_count=column_count,
            )
            for index, column in enumerate(block.columns)
        ]
        col_widths = fit_column_widths(extents=extents, available_width=FRAME_WIDTH)
        numeric_columns = [_is_numeric_column(values=[row.get(column.key) for row in block.rows]) for column in block.columns]
        styles = self._styles
        header_row: list[TableCell] = [
            text_cell(text=column.label, width=col_widths[index], style=styles.cell_header_right if numeric_columns[index] else styles.cell_header)
            for index, column in enumerate(block.columns)
        ]
        body_rows: list[list[TableCell]] = [
            [
                text_cell(text=cell_text, width=col_widths[index], style=styles.cell_right if numeric_columns[index] else styles.cell)
                for index, cell_text in enumerate(displayed_row)
            ]
            for displayed_row in displayed_rows
        ]
        right_aligned_columns = [index for index, is_numeric in enumerate(numeric_columns) if is_numeric]
        table = data_table(rows=[header_row, *body_rows], col_widths=col_widths, has_header=True, right_aligned_columns=right_aligned_columns)
        flowables: list[Flowable] = [self._tagged(flowable=table, origin=f"the table '{block.title}'")]
        if not block.rows:
            flowables.append(Paragraph("No rows.", styles.muted))
        return flowables

    def _image(self, *, block: ImageBlock) -> Flowable:
        self._image_count += 1
        number = self._image_count
        loaded = self._images.get(number=number, url=block.url)
        natural_width = loaded.width_px * _IMAGE_POINTS_PER_PIXEL
        natural_height = loaded.height_px * _IMAGE_POINTS_PER_PIXEL
        scale = min(1.0, FRAME_WIDTH / natural_width, _IMAGE_MAX_HEIGHT / natural_height)
        image = Image(io.BytesIO(loaded.data), width=natural_width * scale, height=natural_height * scale, hAlign="CENTER")
        members: list[Flowable] = [Spacer(1, _IMAGE_SPACE_BEFORE), image]
        if block.caption:
            members.append(Paragraph(escape_text(text=block.caption), self._styles.caption))
        return self._tagged(flowable=KeepTogether(members), origin=f"image {number} of the document")


def _is_numeric_column(*, values: list[LayoutScalar]) -> bool:
    """Whether a column holds numbers only, blanks aside, and at least one: such a column is aligned right."""
    present = [value for value in values if value is not None]
    return bool(present) and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present)


def display_scalar(*, value: LayoutScalar) -> str:
    """A scalar as the document prints it: blank for nothing, Yes or No, numbers plainly, dates and times in ISO order."""
    match value:
        case None:
            return ""
        case bool():
            return "Yes" if value else "No"
        case int():
            return str(value)
        case float():
            if value.is_integer():
                return str(int(value))
            return format(value, ".15g")
        case datetime.datetime():
            return value.strftime("%Y-%m-%d %H:%M")
        case datetime.date():
            return value.isoformat()
        case datetime.time():
            return value.strftime("%H:%M")
        case str():
            return value
