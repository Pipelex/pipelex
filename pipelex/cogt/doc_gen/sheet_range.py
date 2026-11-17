"""Where the rows of a workbook lie: the shared range finder, part of the plugin contract.

A step names the rows it reads or fills in an Excel workbook in one of three ways, and each resolves to a `SheetRegion`,
one rectangular block of cells whose first row is the header row:

- **An Excel Table**, whose reference, header row and totals row count declare its extent (`table_region`).
- **A named range**, a workbook name referring to one rectangular range of cells, its first row the header, which
  declares its extent as a Table does (`resolve_named_range`).
- **A sheet range**, a header row and data rows on a worksheet that nothing declares, found by the rules below
  (`find_sheet_range`), or the one Excel Table its worksheet holds (`resolve_sheet_range`).

Both sides of a spreadsheet resolve a region here: `PipeStructure`'s reader (`pipelex.tools.tabular.xlsx_codec`), which
numbers the region's data rows 1 to n, and a document engine's fill, which appends to the region or updates the rows an
earlier read numbered. One function deciding the range for both is what makes a positional update write the rows the
read numbered, so an engine imports it from here rather than keeping a copy, as it imports the header comparison
(`pipelex.cogt.doc_gen.header_matching`).

**Finding a sheet range.** The finder reads the cells the sheet holds, never its grid: a sheet whose extent a formatted
column stretches to the last row costs what its stored cells cost. A cell holds a value when it holds anything but
nothing or an empty text, a formula included, whatever it calculates to; a cell carrying only formatting holds none. The
worksheet is read with its formulas (opened with `data_only=False`), since the totals line is told by its formula.

1. **The header row** is the row `header_row` names or, without it, the sheet's first row holding a value. A sheet
   holding no value is refused, and so is a `header_row` naming a row that holds none. Rows above the header row are
   not part of the range.
2. **The columns** run from the header row's first cell holding a value, rightwards, to the last cell before the first
   one holding none. A header cell of those columns that belongs to a merged range is refused, naming the merged range;
   a merge elsewhere on the header row is not, by this rule. A value further along the header row, past the empty cell
   that ends the columns, is a second block, refused naming it.
3. **The data rows** run from the row under the header down to the first blank row, which holds no value in any of the
   columns and is not one of them. When the row under the header is blank, the range has no data row, which is valid.
4. **Nothing below.** A value in the columns below that blank row is refused, naming its cell: a further row of data
   after a gap or a note, which the finder cannot tell apart.
5. **No column without a header.** A value in the column just left or just right of the columns, on the header row or
   a row the data rows rule found, a totals line included, is refused as a column with no header. Values further away,
   past that empty column, are another part of the sheet and are left alone.
6. **The totals line.** When a cell of the last row found holds a formula containing a reference to its own column's
   cells, on the same sheet, from the first data row through the row above it, written as a range with a colon
   (`C4:C5`, `$C$4:$C$5`, `Expenses!C4:C5`), that row is a totals line, not a data row (`SheetRegion.totals_row_count`).
   The row under the header is never one, since no data row lies above it.
7. **The filter.** A filter the sheet carries (Data > Filter) must start on the header row and cover the columns found;
   one that disagrees is refused, since the sheet then states its range twice.

Every refusal names the sheet and the cell by its address, such as `Expenses!C12`, or the row, never a cell's value,
which is the run's data, and recommends fixing that cell or turning the range into an Excel Table. Each side bounds the
region's size with its own limit, counted as `SheetRegion.nb_cells`.

**Named ranges.** A name defined for the whole workbook or for one sheet, referring to one rectangular range of at least
two cells on one worksheet by a plain reference. A name holding a formula or a value, several ranges, whole columns or
rows, or cells that no longer exist (`#REF!`) is refused when a step names it, and so is a name defined more than once;
Excel's built-in names (`_xlnm.`) and LibreOffice's hidden database ranges (`__Anonymous_Sheet_DB__`) are never named
ranges. Its first row is its header row, a header cell holding no value naming no column, and every row under it is a
data row, an empty one included, as in a Table; the finder's rules do not apply, since the name declares its extent.

**Refusals.** A range that cannot be told is refused with `TableRangeUnclearError`, carrying the sheet and the cell; a
sheet, a Table or a name that cannot be chosen with `TableSelectionError`. Both are `SHEET_RANGE_REFUSALS`: an engine's
template checker may let either propagate, and Pipelex reports it as an error finding of the check. The `subject` every
function takes is how a message names the workbook, such as "the workbook given for input 'expenses'" or "the input
'workbook'", never its path.

Needs `openpyxl`, which the optional `tabular` extra installs; it is imported only when present, as the reader does.
"""

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.tabular.exceptions import CsvError, CsvReadError, TableRangeUnclearError, TableSelectionError

try:
    from openpyxl.formula.tokenizer import Tokenizer, TokenizerError
    from openpyxl.utils.cell import get_column_letter, range_boundaries
except ImportError:
    Tokenizer = None  # type: ignore[assignment, misc]
    TokenizerError = None  # type: ignore[assignment, misc]
    get_column_letter = None  # type: ignore[assignment]
    range_boundaries = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from openpyxl.cell.cell import Cell
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.table import Table
    from openpyxl.worksheet.worksheet import Worksheet

#: The extra that installs openpyxl, which a missing dependency names.
TABULAR_EXTRA = "tabular"

#: The refusals of this module: an engine's template checker may let them propagate, and the check reports them.
SHEET_RANGE_REFUSALS: tuple[type[CsvError], ...] = (TableRangeUnclearError, TableSelectionError)

#: The beginnings of the names a workbook keeps for itself, which are never named ranges: Excel's built-in names, such as
#: a print area or the range a filter keeps, and the hidden database ranges LibreOffice writes.
BUILT_IN_NAME_PREFIXES: tuple[str, ...] = ("_xlnm.", "__Anonymous_Sheet_DB__")

# The advice every refusal of an unclear range ends with.
_TABLE_REMEDY = "or turn the range into an Excel Table (Insert > Table)"

# A sheet title written bare in a reference; any other is quoted, its quotes doubled.
_BARE_SHEET_TITLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A reference qualified by its sheet: `Sheet1!C4:C5` or `'My sheet'!C4:C5`.
_SHEET_QUALIFIED_REFERENCE = re.compile(r"(?:(?P<bare>[^'!]+)|'(?P<quoted>(?:[^']|'')+)')!(?P<reference>[^!]+)")
# What a named range's definition may be: one area of cells on one sheet, a cell or a range.
_SHEET_PART = r"(?:[A-Za-z0-9_.]+|'(?:[^']|'')+')"
_CELL_PART = r"\$?[A-Za-z]{1,3}\$?[0-9]+"
_ONE_AREA = re.compile(rf"(?P<sheet>{_SHEET_PART})!(?P<first>{_CELL_PART})(?::(?P<last>{_CELL_PART}))?")
_SEVERAL_AREAS = re.compile(rf"{_SHEET_PART}!{_CELL_PART}(?::{_CELL_PART})?(?:,{_SHEET_PART}!{_CELL_PART}(?::{_CELL_PART})?)+")
_WHOLE_LINES = re.compile(rf"{_SHEET_PART}!(?:\$?[A-Za-z]{{1,3}}:\$?[A-Za-z]{{1,3}}|\$?[0-9]+:\$?[0-9]+)")


class SheetRange(BaseModel):
    """A step's `sheet_range`, as plain data: the worksheet a range lies on, and the row holding its header.

    Both are optional: without `sheet`, the workbook must hold exactly one worksheet, and without `header_row`, the
    header is the sheet's first row holding a value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet: str | None = Field(default=None, description="The worksheet, compared ignoring case; None for the workbook's only one")
    header_row: Annotated[int, Field(ge=1, strict=True)] | None = Field(
        default=None, description="The sheet row holding the header, counted from 1; None for the sheet's first row holding a value"
    )


class SheetRangeFill(SheetRange):
    """A `PipeDocGen` step's `sheet_range`: the range, and the list of records that fills it.

    `list` names the list by its path in the step's data, its input's name first, such as `expenses` or
    `report.line_items`. That list fills the range and no Table: an engine takes it out of the binding of lists to
    Tables by name.
    """

    list: str = Field(min_length=1, description="The list of records that fills the range, by its path in the step's data")


class RegionKind(StrEnum):
    """What declares a region's extent."""

    TABLE = "table"
    """An Excel Table: its reference, header row and totals row count."""

    NAMED_RANGE = "named_range"
    """A workbook name referring to one rectangular range."""

    SHEET_RANGE = "sheet_range"
    """Nothing: the finder's rules found it on its worksheet."""


class SheetRegion(BaseModel):
    """Where a region's rows lie on its worksheet, by sheet row and column number, both counted from 1 as Excel does.

    The header row is `header_row`, over the columns `first_column` to `last_column`; the data rows run from the row under
    it to `last_row`, which is `header_row` itself when the region has none; and the `totals_row_count` rows after
    `last_row` are a Table's totals row or a sheet range's totals line, which are not data rows and are not counted in a
    row's position. A Table's and a named range's numbers are what they declare, which may reach past the cells the sheet
    holds; a sheet range's lie within them.

    In a named range, a header cell holding no value names no column, and the cells under it are ignored; in a sheet
    range every header cell holds a value, and a Table's header names every column.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: RegionKind = Field(strict=False)
    name: str | None = Field(description="The Table's name or the workbook name, as the workbook spells it; None for a sheet range")
    sheet_title: str = Field(description="The worksheet the region lies on")
    header_row: int = Field(ge=1)
    first_column: int = Field(ge=1)
    last_column: int = Field(ge=1)
    last_row: int = Field(ge=1, description="The last data row, or the header row when the region has no data row")
    totals_row_count: int = Field(ge=0, description="The rows after the last data row that total it: a Table's totals row, or a totals line")

    @model_validator(mode="after")
    def validate_extent(self) -> Self:
        if self.last_column < self.first_column:
            msg = "A region's last column is not before its first column."
            raise ValueError(msg)
        if self.last_row < self.header_row:
            msg = "A region's last data row is not above its header row."
            raise ValueError(msg)
        if (self.name is None) != (self.kind == RegionKind.SHEET_RANGE):
            msg = "A Table and a named range are named, and a sheet range is not."
            raise ValueError(msg)
        return self

    @property
    def first_data_row(self) -> int:
        return self.header_row + 1

    @property
    def data_rows(self) -> range:
        """The sheet rows of the data rows, in order: row position 1 is the first."""
        return range(self.first_data_row, self.last_row + 1)

    @property
    def columns(self) -> range:
        return range(self.first_column, self.last_column + 1)

    @property
    def totals_rows(self) -> range:
        """The sheet rows of the totals row or line, empty when there is none."""
        return range(self.last_row + 1, self.last_row + 1 + self.totals_row_count)

    @property
    def nb_cells(self) -> int:
        """The cells a region is bounded by: its header row and data rows, times its columns."""
        return (self.last_row - self.header_row + 1) * len(self.columns)

    @property
    def label(self) -> str:
        """The region as a message names it: "the Excel Table 'Expenses'", "the named range 'Expenses'", "the range on the sheet 'Sheet1'"."""
        match self.kind:
            case RegionKind.TABLE:
                return f"the Excel Table '{self.name}'"
            case RegionKind.NAMED_RANGE:
                return f"the named range '{self.name}'"
            case RegionKind.SHEET_RANGE:
                return f"the range on the sheet '{self.sheet_title}'"

    def row_label(self, *, sheet_row: int) -> str:
        """A row of the region as a message names it, by its sheet row: "row 4 of Table 'Expenses'"."""
        match self.kind:
            case RegionKind.TABLE:
                return f"row {sheet_row} of Table '{self.name}'"
            case RegionKind.NAMED_RANGE:
                return f"row {sheet_row} of the named range '{self.name}'"
            case RegionKind.SHEET_RANGE:
                return f"row {sheet_row} of the sheet '{self.sheet_title}'"


def missing_openpyxl_error() -> MissingDependencyError:
    """The refusal of a workbook read or fill where openpyxl is not installed."""
    return MissingDependencyError(
        dependency_name="openpyxl",
        extra_name=TABULAR_EXTRA,
        message="openpyxl is required to read Excel workbooks (.xlsx).",
    )


def cell_address(*, sheet_title: str, row: int, column: int) -> str:
    """A cell's address as a formula writes it, qualified by its sheet: `Expenses!C12`, or `'March 2026'!C12`."""
    if get_column_letter is None:
        raise missing_openpyxl_error()
    return f"{_qualified_sheet_title(sheet_title=sheet_title)}!{get_column_letter(column)}{row}"


def range_address(*, sheet_title: str, first_row: int, first_column: int, last_row: int, last_column: int) -> str:
    """A range's address as a formula writes it, qualified by its sheet: `Expenses!A3:D3`, or `Expenses!A3` for one cell."""
    if get_column_letter is None:
        raise missing_openpyxl_error()
    first = f"{get_column_letter(first_column)}{first_row}"
    last = f"{get_column_letter(last_column)}{last_row}"
    cells = first if first == last else f"{first}:{last}"
    return f"{_qualified_sheet_title(sheet_title=sheet_title)}!{cells}"


def _qualified_sheet_title(*, sheet_title: str) -> str:
    if _BARE_SHEET_TITLE.fullmatch(sheet_title):
        return sheet_title
    escaped_title = sheet_title.replace("'", "''")
    return f"'{escaped_title}'"


def _sentence_start(*, subject: str) -> str:
    """A subject opening a sentence: its first letter capitalized, the rest, an input's name included, as is."""
    return subject[:1].upper() + subject[1:]


def _worksheets(*, workbook: "Workbook") -> list["Worksheet"]:
    # A workbook opened neither read-only nor write-only lists its sheets of cells as `Worksheet`s; a chart sheet, which
    # holds no cells, is not among them.
    return [cast("Worksheet", sheet) for sheet in workbook.worksheets]


def _quoted_names(*, names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names) or "none"


def choose_worksheet(*, workbook: "Workbook", sheet: str | None, subject: str) -> "Worksheet":
    """The worksheet a sheet range lies on: the one `sheet` names, compared ignoring case, or the workbook's only one.

    Raises:
        TableSelectionError: no worksheet has that name, or, without one, the workbook holds several worksheets or none.
    """
    worksheets = _worksheets(workbook=workbook)
    titles = [worksheet.title for worksheet in worksheets]
    if sheet is not None:
        wanted = sheet.casefold()
        for worksheet in worksheets:
            if worksheet.title.casefold() == wanted:
                return worksheet
        msg = f"{_sentence_start(subject=subject)} holds no worksheet named '{sheet}'; its worksheets: {_quoted_names(names=titles)}."
        raise TableSelectionError(msg)
    if len(worksheets) == 1:
        return worksheets[0]
    if not worksheets:
        msg = f"{_sentence_start(subject=subject)} holds no worksheet to read a range of rows from."
        raise TableSelectionError(msg)
    msg = (
        f"{_sentence_start(subject=subject)} holds several worksheets ({_quoted_names(names=titles)}) and the sheet range names none: "
        "name the worksheet with the `sheet` of `sheet_range`."
    )
    raise TableSelectionError(msg)


def table_region(*, worksheet: "Worksheet", table: "Table", subject: str) -> SheetRegion:
    """The region of an Excel Table: what its reference, header row count and totals row count declare.

    Raises:
        CsvReadError: the Table's reference is no range of cells, or the Table has no header row.
    """
    if range_boundaries is None:
        raise missing_openpyxl_error()
    table_label = f"Table '{table.displayName}'"
    min_col, min_row, max_col, max_row = range_boundaries(str(table.ref))
    if min_col is None or min_row is None or max_col is None or max_row is None:
        msg = f"{table_label} of {subject} covers no range of cells."
        raise CsvReadError(msg)
    if table.headerRowCount == 0:
        msg = f"{table_label} of {subject} has no header row; a header naming the columns is required."
        raise CsvReadError(msg)
    totals_row_count = table.totalsRowCount or 0
    last_row = max(max_row - totals_row_count, min_row)
    return SheetRegion(
        kind=RegionKind.TABLE,
        name=str(table.displayName),
        sheet_title=worksheet.title,
        header_row=min_row,
        first_column=min_col,
        last_column=max_col,
        last_row=last_row,
        totals_row_count=max_row - last_row,
    )


def resolve_sheet_range(*, workbook: "Workbook", sheet_range: SheetRange, subject: str) -> SheetRegion:
    """The region a `sheet_range` names: its worksheet's one Excel Table, or the range the finder's rules find on it.

    A worksheet holding exactly one Table is read as that Table, so a method written for plain ranges keeps working when
    a user turns the range into a Table; `header_row`, when given, must then be the Table's header row.

    Raises:
        TableSelectionError: the worksheet cannot be chosen, or it holds several Tables.
        TableRangeUnclearError: `header_row` is not the Table's header row, or the finder's rules refuse the range.
        CsvReadError: the worksheet's one Table has no header row or covers no range of cells.
    """
    worksheet = choose_worksheet(workbook=workbook, sheet=sheet_range.sheet, subject=subject)
    tables = list(worksheet.tables.values())
    if len(tables) > 1:
        names = _quoted_names(names=[str(table.displayName) for table in tables])
        msg = (
            f"The sheet '{worksheet.title}' of {subject} holds several Excel Tables ({names}), and a sheet range reads one range: "
            "name one of the Tables instead of the sheet."
        )
        raise TableSelectionError(msg)
    if tables:
        region = table_region(worksheet=worksheet, table=tables[0], subject=subject)
        if sheet_range.header_row is not None and sheet_range.header_row != region.header_row:
            msg = (
                f"The sheet '{worksheet.title}' of {subject} holds the Excel Table '{region.name}', whose header is row "
                f"{region.header_row}, and the sheet range's `header_row` names row {sheet_range.header_row}: leave `header_row` "
                f"out, or set it to {region.header_row}."
            )
            header_cell = cell_address(sheet_title=worksheet.title, row=region.header_row, column=region.first_column)
            raise TableRangeUnclearError(msg, sheet=worksheet.title, cell=header_cell)
        return region
    return find_sheet_range(worksheet=worksheet, header_row=sheet_range.header_row, subject=subject)


def _holds_value(*, value: Any) -> bool:
    """Whether a cell holds a value: anything but nothing or an empty text, a formula included."""
    return value is not None and value != ""


def _stored_cells(*, worksheet: "Worksheet") -> dict[tuple[int, int], "Cell"]:
    """The cells the sheet stores, by (row, column), without walking its grid.

    openpyxl keeps them in a private mapping and offers no public view of it that does not walk every row and column up
    to the sheet's extent, creating the cells it meets; a sheet's extent is the file's word, and a formatted column
    stretches it to the last of the sheet's 1,048,576 rows.
    """
    return cast("dict[tuple[int, int], Cell]", worksheet._cells)  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[private-member-access]


def find_sheet_range(*, worksheet: "Worksheet", header_row: int | None, subject: str) -> SheetRegion:
    """The range of rows on a worksheet holding no Table, found by the rules of this module's docstring.

    Args:
        worksheet: The worksheet, opened with its formulas (`data_only=False`).
        header_row: The sheet row holding the header, counted from 1; None for the sheet's first row holding a value.
        subject: How messages name the workbook.

    Raises:
        TableRangeUnclearError: the rules cannot settle the range, naming the sheet and the cell.
    """
    if range_boundaries is None:
        raise missing_openpyxl_error()
    title = worksheet.title
    stored_cells = _stored_cells(worksheet=worksheet)
    value_cells = sorted(position for position, cell in stored_cells.items() if _holds_value(value=cell.value))

    def address(*, row: int, column: int) -> str:
        return cell_address(sheet_title=title, row=row, column=column)

    def refuse(*, message: str, row: int | None = None, column: int | None = None) -> TableRangeUnclearError:
        cell = address(row=row, column=column) if row is not None and column is not None else None
        return TableRangeUnclearError(message, sheet=title, cell=cell)

    # 1. The header row.
    if not value_cells:
        msg = (
            f"The sheet '{title}' of {subject} holds no value, so no header row names the columns of a range: write the header "
            "and the rows on it, or name the sheet that holds them."
        )
        raise refuse(message=msg)
    the_header_row = header_row if header_row is not None else value_cells[0][0]
    header_columns = [column for row, column in value_cells if row == the_header_row]
    if not header_columns:
        msg = (
            f"Row {the_header_row} of the sheet '{title}' of {subject}, which `header_row` names, holds no value, so it names no column: "
            "name the row holding the header."
        )
        raise refuse(message=msg)

    # 2. The columns: the run of header cells, a header cell that is merged, and what lies past the run.
    header_column_set = set(header_columns)
    first_column = header_columns[0]
    last_column = first_column
    while last_column + 1 in header_column_set:
        last_column += 1
    header_address = range_address(
        sheet_title=title, first_row=the_header_row, first_column=first_column, last_row=the_header_row, last_column=last_column
    )
    # A header cell of the range that belongs to a merged range: a merge elsewhere on the header row holding a value is
    # refused below as a second block, and one holding none, past the columns, changes nothing.
    for merged_range in sorted(worksheet.merged_cells.ranges, key=lambda cell_range: (cell_range.min_row, cell_range.min_col)):
        if (
            merged_range.min_row <= the_header_row <= merged_range.max_row
            and merged_range.min_col <= last_column
            and merged_range.max_col >= first_column
        ):
            merged_address = range_address(
                sheet_title=title,
                first_row=merged_range.min_row,
                first_column=merged_range.min_col,
                last_row=merged_range.max_row,
                last_column=merged_range.max_col,
            )
            merged_column = max(merged_range.min_col, first_column)
            msg = (
                f"The header cell {address(row=the_header_row, column=merged_column)} of the sheet '{title}' of {subject} belongs to "
                f"the merged cells {merged_address}, and every column needs a header cell of its own: unmerge them, {_TABLE_REMEDY}."
            )
            raise refuse(message=msg, row=the_header_row, column=merged_column)
    past_columns = [column for column in header_columns if column > last_column]
    if past_columns:
        msg = (
            f"The header row {the_header_row} of the sheet '{title}' of {subject} holds a value in "
            f"{address(row=the_header_row, column=past_columns[0])}, past the empty header cell "
            f"{address(row=the_header_row, column=last_column + 1)} that ends the columns {header_address}: a second block of "
            f"columns. Clear that cell or give the empty one a header, {_TABLE_REMEDY}."
        )
        raise refuse(message=msg, row=the_header_row, column=past_columns[0])

    # 3. The data rows, down to the first blank row.
    def in_columns(*, column: int) -> bool:
        return first_column <= column <= last_column

    rows_holding_values = {row for row, column in value_cells if row > the_header_row and in_columns(column=column)}
    last_row = the_header_row
    while last_row + 1 in rows_holding_values:
        last_row += 1

    # 4. Nothing below the blank row that ends them.
    below = [(row, column) for row, column in value_cells if row > last_row and in_columns(column=column)]
    if below:
        below_row, below_column = below[0]
        msg = (
            f"The sheet '{title}' of {subject} holds a value in {address(row=below_row, column=below_column)}, below the blank "
            f"row {last_row + 1} that ends the rows under the header {header_address}: a further row of data after a gap, or a "
            f"note, which the range cannot tell apart. Move or clear that cell, remove the blank row if the data goes on, {_TABLE_REMEDY}."
        )
        if header_row is None:
            msg += " When the header lies lower on the sheet, under a title, name its row with `header_row`."
        raise refuse(message=msg, row=below_row, column=below_column)

    # 5. No column without a header, beside the columns, on the header row or a row found, a totals line included.
    beside = [(row, column) for row, column in value_cells if column in {first_column - 1, last_column + 1} and the_header_row <= row <= last_row]
    if beside:
        beside_row, beside_column = beside[0]
        side = "left" if beside_column < first_column else "right"
        msg = (
            f"The sheet '{title}' of {subject} holds a value in {address(row=beside_row, column=beside_column)}, in the column "
            f"just {side} of the columns {header_address}, whose header cell {address(row=the_header_row, column=beside_column)} "
            f"is empty: a column with no header. Give it a header, clear the column, {_TABLE_REMEDY}."
        )
        raise refuse(message=msg, row=beside_row, column=beside_column)

    # 6. The totals line: never the row under the header, which no data row lies above.
    totals_row_count = 0
    if last_row >= the_header_row + 2:
        for column in range(first_column, last_column + 1):
            cell = stored_cells.get((last_row, column))
            if cell is None or cell.data_type != "f":
                continue
            formula = _formula_text(value=cell.value)
            if formula is not None and _references_column_data(
                formula=formula, sheet_title=title, column=column, first_row=the_header_row + 1, last_row=last_row - 1
            ):
                totals_row_count = 1
                break
    data_last_row = last_row - totals_row_count

    # 7. The filter, when the sheet carries one, states the same range.
    filter_reference = worksheet.auto_filter.ref
    if filter_reference:
        filter_min_col, filter_min_row, filter_max_col, _filter_max_row = range_boundaries(str(filter_reference))
        if filter_min_row != the_header_row or filter_min_col != first_column or filter_max_col != last_column:
            msg = (
                f"The filter of the sheet '{title}' of {subject} covers {filter_reference}, and the range found has its header "
                f"at {header_address}: the sheet states its range in two ways that disagree. Set the filter on the header row, "
                f"remove it, {_TABLE_REMEDY}."
            )
            raise refuse(message=msg)

    return SheetRegion(
        kind=RegionKind.SHEET_RANGE,
        name=None,
        sheet_title=title,
        header_row=the_header_row,
        first_column=first_column,
        last_column=last_column,
        last_row=data_last_row,
        totals_row_count=totals_row_count,
    )


def _formula_text(*, value: Any) -> str | None:
    """A formula cell's formula, `=SUM(C4:C5)`, whether openpyxl holds it as a text or as an array formula."""
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    return text if isinstance(text, str) else None


def _references_column_data(*, formula: str, sheet_title: str, column: int, first_row: int, last_row: int) -> bool:
    """Whether a formula holds a reference, written with a colon, to `column` from `first_row` through `last_row` of its own sheet."""
    if Tokenizer is None or TokenizerError is None or range_boundaries is None:
        raise missing_openpyxl_error()
    try:
        tokens = Tokenizer(formula if formula.startswith("=") else f"={formula}").items
    except TokenizerError:
        return False
    for token in tokens:
        if token.type != "OPERAND" or token.subtype != "RANGE":
            continue
        reference = str(token.value)
        qualified = _SHEET_QUALIFIED_REFERENCE.fullmatch(reference)
        if qualified is not None:
            referenced_sheet = qualified["bare"] or qualified["quoted"].replace("''", "'")
            if referenced_sheet.casefold() != sheet_title.casefold():
                continue
            reference = qualified["reference"]
        if ":" not in reference:
            continue
        try:
            min_col, min_row, max_col, max_row = range_boundaries(reference.replace("$", ""))
        except ValueError:
            continue
        if min_col == max_col == column and min_row == first_row and max_row == last_row:
            return True
    return False


def _is_user_name(*, name: str) -> bool:
    """Whether a workbook name is one its user defined, rather than one the program keeps for itself."""
    return not name.startswith(BUILT_IN_NAME_PREFIXES)


def resolve_named_range(*, workbook: "Workbook", name: str, subject: str) -> SheetRegion | None:
    """The region of the named range `name`, compared ignoring case, or None when the workbook defines no such name.

    Raises:
        TableSelectionError: the name is defined more than once, for several sheets or for the workbook and a sheet.
        TableRangeUnclearError: the name is not a named range: it refers to one cell, holds a formula or a value, refers
            to several ranges, to whole columns or rows, to cells that no longer exist, or to a sheet the workbook does
            not hold as a worksheet.
    """
    if range_boundaries is None:
        raise missing_openpyxl_error()
    wanted = name.casefold()
    definitions: list[tuple[str | None, DefinedName]] = [
        (None, defined_name)
        for defined_key, defined_name in workbook.defined_names.items()
        if _is_user_name(name=str(defined_key)) and str(defined_key).casefold() == wanted
    ]
    worksheets = _worksheets(workbook=workbook)
    for worksheet in worksheets:
        definitions.extend(
            (worksheet.title, defined_name)
            for defined_key, defined_name in worksheet.defined_names.items()
            if _is_user_name(name=str(defined_key)) and str(defined_key).casefold() == wanted
        )
    if not definitions:
        return None
    if len(definitions) > 1:
        scopes = ", ".join("the workbook" if scope is None else f"the sheet '{scope}'" for scope, _ in definitions)
        msg = (
            f"{_sentence_start(subject=subject)} defines the name '{definitions[0][1].name}' more than once, for {scopes}, so it designates no one "
            f"range: keep one definition, {_TABLE_REMEDY}."
        )
        raise TableSelectionError(msg)
    defined_name = definitions[0][1]
    display_name = str(defined_name.name)
    definition = str(defined_name.attr_text).strip().removeprefix("=")
    area = _ONE_AREA.fullmatch(definition)
    remedy = f"make it refer to one range of cells, its first row the header, {_TABLE_REMEDY}"
    if area is None:
        if "#REF!" in definition:
            reason = "refers to cells that no longer exist (#REF!)"
        elif _SEVERAL_AREAS.fullmatch(definition):
            reason = "refers to several ranges"
        elif _WHOLE_LINES.fullmatch(definition):
            reason = "refers to whole columns or rows, which state no extent"
        else:
            reason = "holds a formula or a value rather than a reference to one range of cells"
        msg = f"The name '{display_name}' of {subject} {reason}, so its rows cannot be read or filled: {remedy}."
        raise TableRangeUnclearError(msg, sheet=None, cell=None)
    sheet_part = area["sheet"]
    sheet_title = sheet_part[1:-1].replace("''", "'") if sheet_part.startswith("'") else sheet_part
    named_worksheet = next((candidate for candidate in worksheets if candidate.title.casefold() == sheet_title.casefold()), None)
    if named_worksheet is None:
        msg = (
            f"The name '{display_name}' of {subject} refers to the sheet '{sheet_title}', which the workbook does not hold as a worksheet: {remedy}."
        )
        raise TableRangeUnclearError(msg, sheet=sheet_title, cell=None)
    worksheet = named_worksheet
    first_col, first_row, _, _ = range_boundaries(area["first"].replace("$", ""))
    last_reference = area["last"]
    if last_reference is None:
        last_col, last_row = first_col, first_row
    else:
        last_col, last_row, _, _ = range_boundaries(last_reference.replace("$", ""))
    if first_col is None or first_row is None or last_col is None or last_row is None:
        msg = f"The name '{display_name}' of {subject} refers to no range of cells: {remedy}."
        raise TableRangeUnclearError(msg, sheet=worksheet.title, cell=None)
    min_col, max_col = min(first_col, last_col), max(first_col, last_col)
    min_row, max_row = min(first_row, last_row), max(first_row, last_row)
    if min_col == max_col and min_row == max_row:
        the_cell = cell_address(sheet_title=worksheet.title, row=min_row, column=min_col)
        msg = (
            f"The name '{display_name}' of {subject} refers to the one cell {the_cell}, too small to hold a header and rows: "
            f"make it cover the header and the rows under it, {_TABLE_REMEDY}."
        )
        raise TableRangeUnclearError(msg, sheet=worksheet.title, cell=the_cell)
    return SheetRegion(
        kind=RegionKind.NAMED_RANGE,
        name=display_name,
        sheet_title=worksheet.title,
        header_row=min_row,
        first_column=min_col,
        last_column=max_col,
        last_row=max_row,
        totals_row_count=0,
    )
