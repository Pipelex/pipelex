"""What both writers of the built-in PDF engine share: the bundled fonts, the paragraph styles, the escaping every
text goes through, and the styled tables.

**The bundled fonts.** ReportLab's own fonts are the PDF standard fonts, which print Western European text only, so
the engine bundles open-licensed ones (SIL Open Font License 1.1, whose text sits beside each family in `fonts/`):

- **Open Sans** 3.003, in its four static faces, for every text: Latin with Central European and Vietnamese,
  Greek, Cyrillic and Hebrew. From `googlefonts/opensans` at commit `bd7e37632246368c60fdcbd374dbf9bad11969b6`,
  `fonts/ttf/`.
- **Roboto Mono** 3.001, its regular face only, for code: the scripts of Open Sans except Hebrew, so a comment in
  Polish or Greek inside a code block prints, which ReportLab's Courier would not. From `googlefonts/RobotoMono`
  at commit `895ec691990d041dd727c7b5afa3ce56525d98e6`, `fonts/ttf/`. Its family maps bold and italic to the
  regular face, so inline code inside bold text still resolves.

Right-to-left scripts need ReportLab's optional extras for bidirectional text and shaping (`reportlab[bidi,shaping]`,
which bring `rlbidi` and `uharfbuzz`), which pipelex does not install: without them a Hebrew line prints its letters
left to right. Arabic, Chinese, Japanese and Korean are not in the bundled fonts at all and print as empty boxes.
"""

import re
import threading
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import NamedTuple, TypeAlias
from xml.sax.saxutils import escape

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_CENTER, TA_RIGHT  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.platypus import CondPageBreak, Flowable, Paragraph, Table, TableStyle  # type: ignore[import-untyped]

FONTS_DIR = Path(__file__).parent / "fonts"

# The names the bundled faces are registered under with ReportLab, which are the names paragraph markup uses.
SANS_FONT = "PipelexSans"
SANS_BOLD_FONT = "PipelexSans-Bold"
SANS_ITALIC_FONT = "PipelexSans-Italic"
SANS_BOLD_ITALIC_FONT = "PipelexSans-BoldItalic"
MONO_FONT = "PipelexMono"

TEXT_COLOR = colors.HexColor("#1f2328")
MUTED_COLOR = colors.HexColor("#6b7280")
RULE_COLOR = colors.HexColor("#d0d7de")
HEADER_BACKGROUND_COLOR = colors.HexColor("#f1f3f5")
CODE_BACKGROUND_COLOR = colors.HexColor("#f6f8fa")
LINK_COLOR_HEX = "#1d4ed8"

BODY_FONT_SIZE = 9.5
CELL_FONT_SIZE = 8.5
CELL_LEADING = 11.0
CELL_HORIZONTAL_PADDING = 4.0
CELL_VERTICAL_PADDING = 3.0
BOX_PADDING = 6.0

# A heading starts a new page when less than this height is left below it, so it is never left alone at the foot of a
# page. ReportLab's `keepWithNext` is not used for that: it keeps a heading with everything that follows it, so a
# heading before a long table would push the whole table onto the next page.
HEADING_ROOM = 72.0

# What a table cell holds: a flowable, or a text ReportLab draws as it is, in the table's own font.
TableCell: TypeAlias = Flowable | str


class BundledFace(NamedTuple):
    font_name: str
    file_path: Path


BUNDLED_FACES: tuple[BundledFace, ...] = (
    BundledFace(font_name=SANS_FONT, file_path=FONTS_DIR / "open-sans" / "OpenSans-Regular.ttf"),
    BundledFace(font_name=SANS_BOLD_FONT, file_path=FONTS_DIR / "open-sans" / "OpenSans-Bold.ttf"),
    BundledFace(font_name=SANS_ITALIC_FONT, file_path=FONTS_DIR / "open-sans" / "OpenSans-Italic.ttf"),
    BundledFace(font_name=SANS_BOLD_ITALIC_FONT, file_path=FONTS_DIR / "open-sans" / "OpenSans-BoldItalic.ttf"),
    BundledFace(font_name=MONO_FONT, file_path=FONTS_DIR / "roboto-mono" / "RobotoMono-Regular.ttf"),
)

_FONT_REGISTRATION_LOCK = threading.Lock()


def register_bundled_fonts() -> None:
    """Register the bundled faces and their families with ReportLab, once per process, whichever thread asks first.

    ReportLab keeps registered fonts in a process-wide table, so a second registration would swap the font objects
    under a render already using them: the lock and the cache make it happen exactly once.
    """
    with _FONT_REGISTRATION_LOCK:
        _register_bundled_fonts_once()


@cache
def _register_bundled_fonts_once() -> None:
    # The stubs leave some of these functions' parameters untyped, hence the ignores.
    for face in BUNDLED_FACES:
        pdfmetrics.registerFont(TTFont(face.font_name, str(face.file_path)))  # pyright: ignore[reportUnknownMemberType]
    pdfmetrics.registerFontFamily(  # pyright: ignore[reportUnknownMemberType]
        SANS_FONT, normal=SANS_FONT, bold=SANS_BOLD_FONT, italic=SANS_ITALIC_FONT, boldItalic=SANS_BOLD_ITALIC_FONT
    )
    pdfmetrics.registerFontFamily(MONO_FONT, normal=MONO_FONT, bold=MONO_FONT, italic=MONO_FONT, boldItalic=MONO_FONT)  # pyright: ignore[reportUnknownMemberType]


class PdfStyles(NamedTuple):
    """The paragraph styles of the engine, built once per renderer, after the fonts are registered."""

    title: ParagraphStyle
    headings: tuple[ParagraphStyle, ...]
    body: ParagraphStyle
    list_body: ParagraphStyle
    cell: ParagraphStyle
    cell_right: ParagraphStyle
    cell_center: ParagraphStyle
    cell_header: ParagraphStyle
    cell_header_right: ParagraphStyle
    cell_header_center: ParagraphStyle
    grid_label: ParagraphStyle
    caption: ParagraphStyle
    muted: ParagraphStyle
    code: ParagraphStyle

    def heading(self, *, level: int) -> ParagraphStyle:
        """The heading style of a level, clamped to the levels there are: 1 is the largest, deeper ones the smallest."""
        clamped_level = min(max(level, 1), len(self.headings))
        return self.headings[clamped_level - 1]


def build_pdf_styles() -> PdfStyles:
    body = ParagraphStyle(
        "pipelex-body",
        fontName=SANS_FONT,
        fontSize=BODY_FONT_SIZE,
        leading=13.5,
        textColor=TEXT_COLOR,
        spaceAfter=5,
    )
    heading_sizes = (16.0, 13.5, 12.0, 11.0, 10.0, 9.5)
    headings = tuple(
        ParagraphStyle(
            f"pipelex-heading-{index}",
            parent=body,
            fontName=SANS_BOLD_FONT,
            fontSize=size,
            leading=size * 1.3,
            spaceBefore=size * 0.7,
            spaceAfter=size * 0.35,
        )
        for index, size in enumerate(heading_sizes, start=1)
    )
    cell = ParagraphStyle("pipelex-cell", parent=body, fontSize=CELL_FONT_SIZE, leading=CELL_LEADING, spaceAfter=0)
    cell_header = ParagraphStyle("pipelex-cell-header", parent=cell, fontName=SANS_BOLD_FONT)
    return PdfStyles(
        title=ParagraphStyle("pipelex-title", parent=body, fontName=SANS_BOLD_FONT, fontSize=20, leading=25, spaceAfter=10),
        headings=headings,
        body=body,
        list_body=ParagraphStyle("pipelex-list-body", parent=body, spaceAfter=2),
        cell=cell,
        cell_right=ParagraphStyle("pipelex-cell-right", parent=cell, alignment=TA_RIGHT),
        cell_center=ParagraphStyle("pipelex-cell-center", parent=cell, alignment=TA_CENTER),
        cell_header=cell_header,
        cell_header_right=ParagraphStyle("pipelex-cell-header-right", parent=cell_header, alignment=TA_RIGHT),
        cell_header_center=ParagraphStyle("pipelex-cell-header-center", parent=cell_header, alignment=TA_CENTER),
        grid_label=ParagraphStyle("pipelex-grid-label", parent=body, fontName=SANS_BOLD_FONT, spaceAfter=0),
        caption=ParagraphStyle(
            "pipelex-caption",
            parent=body,
            fontName=SANS_ITALIC_FONT,
            fontSize=8.5,
            leading=11,
            textColor=MUTED_COLOR,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=10,
        ),
        muted=ParagraphStyle("pipelex-muted", parent=body, fontName=SANS_ITALIC_FONT, textColor=MUTED_COLOR),
        code=ParagraphStyle("pipelex-code", parent=body, fontName=MONO_FONT, fontSize=8, leading=10.5, spaceAfter=0),
    )


# C0 control characters other than tab, line feed and carriage return, and DEL: they have no glyph and no meaning in
# a printed page, so they are dropped rather than handed to ReportLab's parser.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def escape_text(*, text: str) -> str:
    """A text as ReportLab paragraph markup that prints it literally, its line breaks kept.

    Every text a writer puts into a paragraph goes through here, so a value such as `<b>Tom & Jerry</b>` prints as
    written and can never open a tag of ReportLab's markup.
    """
    cleaned = _CONTROL_CHARACTERS.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    return escape(cleaned).replace("\n", "<br/>")


def escape_attribute(*, value: str) -> str:
    """A value for a double-quoted attribute of ReportLab's paragraph markup, such as a link's `href`."""
    return escape(_CONTROL_CHARACTERS.sub("", value), {'"': "&quot;"})


class TextExtent(NamedTuple):
    """How wide a text is when set on one line per line break, and how wide its widest word is, in points."""

    line_width: float
    word_width: float


def measure_text(*, text: str, font_name: str, font_size: float) -> TextExtent:
    line_width = 0.0
    word_width = 0.0
    for line in text.splitlines() or [""]:
        line_width = max(line_width, pdfmetrics.stringWidth(line, font_name, font_size))
        for word in line.split():
            word_width = max(word_width, pdfmetrics.stringWidth(word, font_name, font_size))
    return TextExtent(line_width=line_width, word_width=word_width)


class ColumnExtent(NamedTuple):
    """The widths a table column would like, in points, cell padding included."""

    preferred: float
    minimum: float


# A table measures at most this many rows to size its columns, so a table of thousands of rows costs no more to
# size than one of a few hundred.
_MEASURED_ROWS_LIMIT = 300
_MINIMUM_COLUMN_WIDTH = 24.0


def measure_column(*, header: str | None, cells: Iterable[str], available_width: float, column_count: int) -> ColumnExtent:
    """The preferred and minimum widths of a column, from its header and the text of its cells.

    The minimum is the widest word, which is capped at an even share of the width, so a long URL wraps inside its
    cell rather than squeezing every other column.
    """
    padding = 2 * CELL_HORIZONTAL_PADDING
    extents: list[TextExtent] = []
    if header is not None:
        extents.append(measure_text(text=header, font_name=SANS_BOLD_FONT, font_size=CELL_FONT_SIZE))
    for index, cell_text in enumerate(cells):
        if index >= _MEASURED_ROWS_LIMIT:
            break
        extents.append(measure_text(text=cell_text, font_name=SANS_FONT, font_size=CELL_FONT_SIZE))
    preferred = max((extent.line_width for extent in extents), default=0.0) + padding
    minimum = max((extent.word_width for extent in extents), default=0.0) + padding
    share = available_width / max(column_count, 1)
    minimum = min(max(minimum, _MINIMUM_COLUMN_WIDTH), share)
    return ColumnExtent(preferred=max(preferred, minimum), minimum=minimum)


def fit_column_widths(*, extents: list[ColumnExtent], available_width: float) -> list[float]:
    """Column widths that fit the available width.

    Columns keep their preferred widths when they all fit. Otherwise every column gets its minimum, and the width
    left is shared out evenly: a column that wants less than an even share takes what it wants, and the columns that
    want more split what remains. So a column of long text wraps, and the short columns beside it do not. When even
    the minimums do not fit, they shrink in proportion.
    """
    total_preferred = sum(extent.preferred for extent in extents)
    if total_preferred <= available_width:
        return [extent.preferred for extent in extents]
    total_minimum = sum(extent.minimum for extent in extents)
    if total_minimum >= available_width:
        return [extent.minimum * available_width / total_minimum for extent in extents]
    widths = [extent.minimum for extent in extents]
    extra_width = available_width - total_minimum
    wanting = list(range(len(extents)))
    while wanting:
        share = extra_width / len(wanting)
        satisfied = [index for index in wanting if extents[index].preferred - widths[index] <= share]
        if not satisfied:
            for index in wanting:
                widths[index] += share
            break
        for index in satisfied:
            extra_width -= extents[index].preferred - widths[index]
            widths[index] = extents[index].preferred
        wanting = [index for index in wanting if index not in satisfied]
    return widths


def heading_break() -> Flowable:
    """What goes before a heading so that it starts a new page rather than end one (`HEADING_ROOM`)."""
    return CondPageBreak(HEADING_ROOM)


def text_cell(*, text: str, width: float, style: ParagraphStyle) -> TableCell:
    """A table cell printing a text in a column `width` points wide.

    A text that fits on one line is the cell itself, which ReportLab draws as it is, in the font the table style
    sets for the cell (`data_table`), with no paragraph to lay out: that is what keeps a long table fast. A text
    that does not fit becomes a paragraph, escaped, which wraps.
    """
    cleaned = _CONTROL_CHARACTERS.sub("", text)
    if "\n" not in cleaned and "\r" not in cleaned:
        if pdfmetrics.stringWidth(cleaned, style.fontName, style.fontSize) <= width - 2 * CELL_HORIZONTAL_PADDING:
            return cleaned
    return Paragraph(escape_text(text=cleaned), style)


def data_table(*, rows: list[list[TableCell]], col_widths: list[float], has_header: bool, right_aligned_columns: list[int]) -> Table:
    """A table of cells: its header row repeats on every page, and a row taller than a page splits.

    Its style sets the font of the cells that are plain texts (`text_cell`): the cell face and size, bold in the
    header row, and right-aligned in `right_aligned_columns`. Paragraph cells carry their own style.
    """
    table = Table(
        rows,
        colWidths=col_widths,
        repeatRows=1 if has_header else 0,
        splitInRow=1,
        hAlign="LEFT",
        spaceBefore=2,
        spaceAfter=8,
    )
    table_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), CELL_HORIZONTAL_PADDING),
            ("RIGHTPADDING", (0, 0), (-1, -1), CELL_HORIZONTAL_PADDING),
            ("TOPPADDING", (0, 0), (-1, -1), CELL_VERTICAL_PADDING),
            ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_VERTICAL_PADDING),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE_COLOR),
            ("FONTNAME", (0, 0), (-1, -1), SANS_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), CELL_FONT_SIZE),
            ("LEADING", (0, 0), (-1, -1), CELL_LEADING),
            ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_COLOR),
        ]
    )
    for column_index in right_aligned_columns:
        table_style.add("ALIGN", (column_index, 0), (column_index, -1), "RIGHT")
    if has_header:
        table_style.add("FONTNAME", (0, 0), (-1, 0), SANS_BOLD_FONT)
        table_style.add("BACKGROUND", (0, 0), (-1, 0), HEADER_BACKGROUND_COLOR)
        table_style.add("LINEBELOW", (0, 0), (-1, 0), 0.6, MUTED_COLOR)
    table.setStyle(table_style)
    return table


def field_grid_table(*, rows: list[list[Flowable]], col_widths: list[float]) -> Table:
    """A two-column table of labels and values, with no header, which splits between rows and inside a tall row."""
    table = Table(rows, colWidths=col_widths, splitInRow=1, hAlign="LEFT", spaceBefore=2, spaceAfter=8)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * CELL_HORIZONTAL_PADDING),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def boxed(*, flowables: list[Flowable], width: float, is_code: bool) -> Table:
    """Flowables in a box the width of the frame: shaded for code, with a rule on the left for a quotation.

    A one-cell table rather than a frame of its own, so the box splits across pages with its content.
    """
    table = Table([[flowables]], colWidths=[width], splitInRow=1, hAlign="LEFT", spaceBefore=2, spaceAfter=8)
    table_style = TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), BOX_PADDING),
            ("RIGHTPADDING", (0, 0), (-1, -1), BOX_PADDING),
            ("TOPPADDING", (0, 0), (-1, -1), BOX_PADDING if is_code else 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), BOX_PADDING if is_code else 1),
        ]
    )
    if is_code:
        table_style.add("BACKGROUND", (0, 0), (-1, -1), CODE_BACKGROUND_COLOR)
    else:
        table_style.add("LINEBEFORE", (0, 0), (0, -1), 2, RULE_COLOR)
    table.setStyle(table_style)
    return table
