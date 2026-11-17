"""Excel codec — reads one region of an Office Open XML workbook (`.xlsx`) into a `RawTable`.

Needs `openpyxl`, which the optional `tabular` extra installs (`pipelex[tabular]`). The codec reads; matching the header
to a row concept's fields and binding the rows are format-neutral (`pipelex.tools.tabular.table_records`).

**The region.** Rows are read from one rectangular region whose first row is the header row, chosen by the step's
`TableSelector` and resolved by the range finder the reader shares with the document engines
(`pipelex.cogt.doc_gen.sheet_range`):

- `table` names an Excel Table, compared ignoring case as Excel compares Table names, or, when the workbook holds no
  Table of that name, a named range. A workbook holding neither is refused, naming the Tables found.
- `sheet_range` names a range on a worksheet: the worksheet's one Table when it holds one, and otherwise the range the
  finder's rules find, the finder reading the workbook's formulas, since a totals line is told by its formula.
- With neither, the workbook's only Table is read; several Tables or none are refused, naming the Tables found, and
  the refusal of a workbook holding none suggests `sheet_range`. Named ranges never count toward this default.

The region's header row names the columns, and a named range's header cell holding no value names none; the rows
between the header and the region's last data row are its data rows, and a Table's totals row or a sheet range's
totals line is not read.

**The values.** Each cell is read with its type, a number as a number, a date as a date (a `datetime`, as openpyxl
reads one), a boolean as a boolean and a text as a text. A time or a duration, which no row field holds, is read as its
text. A formula cell is read as the value the workbook last calculated and stored for it. A workbook saved by a program
that stores none, such as one written by openpyxl itself, has no such value: the cell reads as empty, and the column is
reported so the step can warn (`RawTable.uncached_formula_columns`).

**The rows.** Every data row of the region is a row of the table, an empty one of a Table or a named range included,
named in messages by its sheet row, as Excel shows it.

**The limits.** The file chooses its own size, so two bounds (`TableReadingConfig`) are checked before any cell is read:
the bytes the workbook's parts hold once decompressed, summed from its archive's directory before anything is
decompressed, and the cells the region spans: its header row and every declared data row, times the columns within the
sheet's extent, at least one. Cells are read only within the sheet's own extent, whatever range a Table or a name
declares, and a region with no column inside it, which has no header cell, is refused.
"""

import io
import zipfile
import zlib
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from pipelex.cogt.doc_gen.sheet_range import (
    RegionKind,
    SheetRegion,
    missing_openpyxl_error,
    resolve_named_range,
    resolve_sheet_range,
    table_region,
    workbook_worksheets,
)
from pipelex.tools.tabular.exceptions import CsvReadError, TableSelectionError, TableTooLargeError
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_records import RawTable, RawTableRow, TableBinding, TableCellValue, sentence_subject
from pipelex.tools.tabular.table_selector import TableSelector

try:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException
except ImportError:
    openpyxl = None  # type: ignore[assignment]
    InvalidFileException = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.table import Table
    from openpyxl.worksheet.worksheet import Worksheet

# What tells a workbook among zip archives: the content type its package declares for its main part, and the part's name.
_CONTENT_TYPES_PART = "[Content_Types].xml"
_SPREADSHEET_MAIN_CONTENT_TYPE = b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_WORKBOOK_PART = "xl/workbook.xml"
# The most bytes the content types part is read to, decompressed, judged from the size the archive declares for it; a
# workbook's lists a few dozen parts in a few kilobytes.
_MAX_CONTENT_TYPES_BYTES = 1_000_000


def is_xlsx_reader_available() -> bool:
    """Whether openpyxl, which the `tabular` extra installs, can be imported, so `.xlsx` workbooks can be read."""
    return openpyxl is not None


def is_xlsx_archive(*, raw_bytes: bytes) -> bool:
    """Whether a zip archive's bytes are an Excel workbook, by its package's declared main content type or its parts.

    A sniffer names a workbook only when its identifying entry sits among the archive's first few, so a workbook whose
    entries come in another order sniffs as a bare zip. Its directory says more: a workbook's `[Content_Types].xml`
    declares the spreadsheet main part, and the part is `xl/workbook.xml`. Only the directory and, when the archive
    declares it no larger than a bound, the content types part are read; bytes that are no readable zip are no workbook.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            names = set(archive.namelist())
            if _WORKBOOK_PART in names:
                return True
            if _CONTENT_TYPES_PART not in names:
                return False
            content_types_info = archive.getinfo(_CONTENT_TYPES_PART)
            if content_types_info.file_size > _MAX_CONTENT_TYPES_BYTES:
                return False
            return _SPREADSHEET_MAIN_CONTENT_TYPE in archive.read(content_types_info)
    # A zip the directory of which is unreadable, or a part that does not decompress: no workbook a read could open.
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError, zlib.error):
        return False


def xlsx_subject(*, input_name: str | None) -> str:
    """How a message names the workbook it refuses: by the input it was given as, never by its path, which is the caller's."""
    return f"the workbook given for input '{input_name}'" if input_name is not None else "the workbook"


def read_xlsx_raw_table(
    *, raw_bytes: bytes, table_selector: TableSelector, binding: TableBinding, limits: TableReadingConfig, subject: str
) -> RawTable:
    """Read the region of a workbook's bytes a step names into a `RawTable`.

    Args:
        raw_bytes: The workbook's bytes.
        table_selector: The Table or named range to read, the range on a sheet, or neither for the workbook's only Table.
        binding: Whose rules the table is read under, which decides whether a refusal may tell its reader to name a region.
        limits: How large a workbook, and a region, may be read.
        subject: How messages name the workbook.

    Returns:
        The region's header and data rows, typed, with the columns holding a formula without a cached value.

    Raises:
        MissingDependencyError: openpyxl is not installed.
        CsvReadError: The bytes are not a workbook openpyxl can open, or the region has no header cell.
        TableSelectionError: The region cannot be chosen, as the module says.
        TableRangeUnclearError: The sheet range's rules, or the named range's, refuse the region.
        TableTooLargeError: The workbook's parts, decompressed, or the region's cells, pass the limits.
    """
    _refuse_oversized_archive(raw_bytes=raw_bytes, max_uncompressed_bytes=limits.max_workbook_uncompressed_bytes, subject=subject)
    value_workbook = _load_workbook(raw_bytes=raw_bytes, data_only=True, subject=subject)
    formula_workbook: Workbook | None = None
    region: SheetRegion
    if table_selector.sheet_range is not None:
        # The finder tells a cell holding a value, and a totals line, by its formula, which the cached values hide: a
        # formula with no cached value reads as empty there.
        formula_workbook = _load_workbook(raw_bytes=raw_bytes, data_only=False, subject=subject)
        region = resolve_sheet_range(workbook=formula_workbook, sheet_range=table_selector.sheet_range, subject=subject)
    else:
        region = _choose_region(workbook=value_workbook, table_name=table_selector.table, binding=binding, subject=subject)
    worksheet = value_workbook[region.sheet_title]
    region_label = region.short_label
    header_row = region.header_row
    last_data_row = region.last_row

    # The declared range is the file's word, and a crafted one can span the whole sheet: cells are only ever read within
    # the sheet's own extent. A column past it holds no cell, its header included, so it is no column of the table. A row
    # past it is still a data row of the Table or the named range, as the standard makes every declared row one, whose
    # cells are all empty: it counts toward the row position, and is made without reading the sheet, but it is a record
    # the read builds, so every declared row counts toward the cap, at least one cell wide even when no column lies within
    # the sheet. A sheet range lies within the sheet's cells, which the finder found it among.
    sheet_last_row = worksheet.max_row
    declared_columns = range(region.first_column, min(region.last_column, worksheet.max_column) + 1)
    nb_declared_rows = last_data_row - header_row + 1
    nb_cells = nb_declared_rows * max(len(declared_columns), 1)
    if nb_cells > limits.max_table_cells:
        msg = (
            f"{sentence_subject(subject=region_label)} of {subject} spans {nb_cells} cells, more than the {limits.max_table_cells} "
            "a table is read with ([runtime.table_reading] max_table_cells): read a smaller table."
        )
        raise TableTooLargeError(msg)
    columns = list(declared_columns)
    if region.kind == RegionKind.NAMED_RANGE:
        # A named range's header cell holding no value names no column, and the cells under it are not read.
        columns = [column for column in columns if _cell_value(value=worksheet.cell(row=header_row, column=column).value) is not None]
    if not columns:
        msg = f"{sentence_subject(subject=region_label)} of {subject} has no column within the sheet's cells, so no header cell names one."
        raise CsvReadError(msg)

    header = [_header_text(value=worksheet.cell(row=header_row, column=column).value) for column in columns]
    uncached_candidates: list[tuple[int, int]] = []
    rows: list[RawTableRow] = []
    for sheet_row in region.data_rows:
        row_label = region.row_label(sheet_row=sheet_row)
        if sheet_row > sheet_last_row:
            rows.append(RawTableRow(label=row_label, cells=[None] * len(columns)))
            continue
        cells: list[TableCellValue] = []
        for column_index, column in enumerate(columns):
            cell = worksheet.cell(row=sheet_row, column=column)
            # A formula with no cached value reads as no value of numeric type, as an empty cell does; a formula whose
            # cached value is an empty text reads as no value of type `str`, and was calculated, so it is no candidate.
            if cell.value is None and cell.data_type == "n":
                uncached_candidates.append((sheet_row, column_index))
            cells.append(_cell_value(value=cell.value))
        rows.append(RawTableRow(label=row_label, cells=cells))

    uncached_formula_columns = _uncached_formula_columns(
        raw_bytes=raw_bytes,
        formula_workbook=formula_workbook,
        sheet_title=worksheet.title,
        columns=columns,
        empty_cells=uncached_candidates,
        subject=subject,
    )
    return RawTable(header=header, rows=rows, uncached_formula_columns=uncached_formula_columns)


def _refuse_oversized_archive(*, raw_bytes: bytes, max_uncompressed_bytes: int, subject: str) -> None:
    """Refuse a workbook whose parts, decompressed, would hold more bytes than the limit, before decompressing any.

    The sizes are the ones the archive's directory declares, which bound what reading a part yields: Python's ZIP reader
    stops a part at its declared size.

    Raises:
        CsvReadError: The bytes are not a ZIP archive.
        TableTooLargeError: The declared sizes sum past the limit.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            uncompressed_bytes = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError) as exc:
        msg = f"Could not open {subject} as an Excel workbook (.xlsx): {type(exc).__name__}"
        raise CsvReadError(msg) from exc
    if uncompressed_bytes > max_uncompressed_bytes:
        msg = (
            f"{sentence_subject(subject=subject)} holds {uncompressed_bytes} bytes once decompressed, more than the {max_uncompressed_bytes} "
            "a workbook is read with ([runtime.table_reading] max_workbook_uncompressed_bytes)."
        )
        raise TableTooLargeError(msg, limit_bytes=max_uncompressed_bytes, size_bytes=uncompressed_bytes)


def _load_workbook(*, raw_bytes: bytes, data_only: bool, subject: str) -> "Workbook":
    """Open a workbook's bytes, wrapping what openpyxl raises on a file it cannot open as `CsvReadError`."""
    if openpyxl is None or InvalidFileException is None:
        raise missing_openpyxl_error()
    try:
        return openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=data_only)
    # openpyxl raises these on a file that is not a workbook: a zip it cannot open, a zip missing a part it needs, or a part
    # it cannot parse, an XML part that is not well formed raising a `SyntaxError` (the standard library's `ParseError`
    # and lxml's `XMLSyntaxError` both subclass it). None of their texts is quoted, since they can carry the file's own
    # content.
    except (zipfile.BadZipFile, InvalidFileException, KeyError, ValueError, OSError, SyntaxError) as exc:
        msg = f"Could not open {subject} as an Excel workbook (.xlsx): {type(exc).__name__}"
        raise CsvReadError(msg) from exc


def _choose_region(*, workbook: "Workbook", table_name: str | None, binding: TableBinding, subject: str) -> SheetRegion:
    """The region to read when the step names no sheet range: the Table or named range named, or the workbook's only Table.

    A refusal tells a step's author how to name the region, with `table` or `sheet_range`; a run input names none, so its
    refusal says what the workbook must hold instead.
    """
    found: list[tuple[Worksheet, Table]] = []
    for worksheet in workbook_worksheets(workbook=workbook):
        found.extend((worksheet, table) for table in worksheet.tables.values())
    found_names = ", ".join(f"'{table.displayName}'" for _, table in found) or "none"
    if table_name is not None:
        wanted = table_name.casefold()
        for found_worksheet, found_table in found:
            if found_table.displayName.casefold() == wanted or (found_table.name or "").casefold() == wanted:
                return table_region(worksheet=found_worksheet, table=found_table, subject=subject)
        # Excel keeps Table names and workbook names in one namespace, so a name that is no Table's may be a named range.
        named_region = resolve_named_range(workbook=workbook, name=table_name, subject=subject)
        if named_region is not None:
            return named_region
        msg = f"{sentence_subject(subject=subject)} holds no Table or named range named '{table_name}'; the Tables it holds: {found_names}."
        raise TableSelectionError(msg)
    if len(found) == 1:
        found_worksheet, found_table = found[0]
        return table_region(worksheet=found_worksheet, table=found_table, subject=subject)
    if not found:
        msg = f"{sentence_subject(subject=subject)} holds no Excel Table: define the rows to read as a Table (Insert > Table) in the workbook"
        msg += ", or read them from a range on a sheet with `sheet_range`." if binding.names_its_region else "."
        raise TableSelectionError(msg)
    if binding.names_its_region:
        msg = (
            f"{sentence_subject(subject=subject)} holds several Tables ({found_names}) and the step names none: name the Table to read with `table`."
        )
    else:
        msg = (
            f"{sentence_subject(subject=subject)} holds several Tables ({found_names}), and a workbook given as an input is read from its "
            "only Table: keep the rows to read in one Table of the workbook."
        )
    raise TableSelectionError(msg)


def _uncached_formula_columns(
    *,
    raw_bytes: bytes,
    formula_workbook: "Workbook | None",
    sheet_title: str,
    columns: list[int],
    empty_cells: list[tuple[int, int]],
    subject: str,
) -> frozenset[int]:
    """The columns, by 0-based index among `columns`, of the empty cells that hold a formula: formulas with no cached value.

    `empty_cells` are the cells that read no value of numeric type, the way both an empty cell and an uncached formula
    read; a formula whose cached value is an empty text is not among them. The workbook's formulas are read from
    `formula_workbook` when the read already opened it, and otherwise from a second opening, made only when some cell is.
    """
    if not empty_cells:
        return frozenset()
    if formula_workbook is None:
        formula_workbook = _load_workbook(raw_bytes=raw_bytes, data_only=False, subject=subject)
    formula_worksheet = formula_workbook[sheet_title]
    found_columns: set[int] = set()
    for sheet_row, column_index in empty_cells:
        if formula_worksheet.cell(row=sheet_row, column=columns[column_index]).data_type == "f":
            found_columns.add(column_index)
    return frozenset(found_columns)


def _header_text(*, value: Any) -> str:
    """A header cell as the text a field is matched with: a number or a date heading a column reads as its text."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _cell_value(*, value: Any) -> TableCellValue:
    """A cell's value as a row reads it: typed, an empty text as None, a time or a duration as its text."""
    if value is None or value == "":
        return None
    if isinstance(value, (bool, int, float, datetime, date, str)):
        return value
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    return str(value)
