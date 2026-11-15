"""Excel codec — reads one Table of an Office Open XML workbook (`.xlsx`) into a `RawTable`.

Needs `openpyxl`, which the optional `tabular` extra installs (`pipelex[tabular]`). The codec reads; matching the header
to a row concept's fields and binding the rows are format-neutral (`pipelex.tools.tabular.table_records`).

**The Table.** Rows are read from an Excel Table, the named table object a workbook defines over a range of cells with a
header row: the one named, compared ignoring case as Excel compares Table names, or the workbook's only Table when none
is named. A workbook with no Table of the name given, or, with no name, several Tables or none, is refused, and the
refusal names the Tables found. The Table's header row names the columns; the rows between it and the end of the Table
are its data rows, and a totals row is not read.

**The values.** Each cell is read with its type, a number as a number, a date as a date (a `datetime`, as openpyxl
reads one), a boolean as a boolean and a text as a text. A time or a duration, which no row field holds, is read as its
text. A formula cell is read as the value the workbook last calculated and stored for it. A workbook saved by a program
that stores none, such as one written by openpyxl itself, has no such value: the cell reads as empty, and the column is
reported so the step can warn (`RawTable.uncached_formula_columns`).

**The rows.** Every data row of the Table is a row of the table, an empty one included, named in messages by its sheet
row, as Excel shows it.
"""

import io
import zipfile
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, cast

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.tabular.exceptions import CsvReadError, TableSelectionError
from pipelex.tools.tabular.table_records import RawTable, RawTableRow, TableCellValue

try:
    import openpyxl
    from openpyxl.utils.cell import range_boundaries
    from openpyxl.utils.exceptions import InvalidFileException
except ImportError:
    openpyxl = None  # type: ignore[assignment]
    range_boundaries = None  # type: ignore[assignment]
    InvalidFileException = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.table import Table
    from openpyxl.worksheet.worksheet import Worksheet

# The extra that installs openpyxl, which a missing dependency names.
TABULAR_EXTRA = "tabular"


def is_xlsx_reader_available() -> bool:
    """Whether openpyxl, which the `tabular` extra installs, can be imported, so `.xlsx` workbooks can be read."""
    return openpyxl is not None


def xlsx_subject(*, input_name: str | None) -> str:
    """How a message names the workbook it refuses: by the input it was given as, never by its path, which is the caller's."""
    return f"the workbook given for input '{input_name}'" if input_name is not None else "the workbook"


def read_xlsx_raw_table(*, raw_bytes: bytes, table_name: str | None, subject: str) -> RawTable:
    """Read one Table of a workbook's bytes into a `RawTable`.

    Args:
        raw_bytes: The workbook's bytes.
        table_name: The Table to read, compared ignoring case; None to read the workbook's only Table.
        subject: How messages name the workbook.

    Returns:
        The Table's header and data rows, typed, with the columns holding a formula without a cached value.

    Raises:
        MissingDependencyError: openpyxl is not installed.
        CsvReadError: The bytes are not a workbook openpyxl can open, or the Table has no header row.
        TableSelectionError: The Table cannot be chosen, as the module says.
    """
    value_workbook = _load_workbook(raw_bytes=raw_bytes, data_only=True, subject=subject)
    worksheet, table = _choose_table(workbook=value_workbook, table_name=table_name, subject=subject)
    table_label = f"Table '{table.displayName}'"
    if range_boundaries is None:
        raise _missing_openpyxl()
    min_col, min_row, max_col, max_row = range_boundaries(table.ref)
    if min_col is None or min_row is None or max_col is None or max_row is None:
        msg = f"{table_label} of {subject} covers no range of cells."
        raise CsvReadError(msg)
    if table.headerRowCount == 0:
        msg = f"{table_label} of {subject} has no header row; a header naming the columns is required."
        raise CsvReadError(msg)
    totals_row_count = table.totalsRowCount or 0
    first_data_row = min_row + 1
    last_data_row = max_row - totals_row_count
    columns = range(min_col, max_col + 1)

    header = [_header_text(value=worksheet.cell(row=min_row, column=column).value) for column in columns]
    empty_cells: list[tuple[int, int]] = []
    rows: list[RawTableRow] = []
    for sheet_row in range(first_data_row, last_data_row + 1):
        cells: list[TableCellValue] = []
        for column_index, column in enumerate(columns):
            value = _cell_value(value=worksheet.cell(row=sheet_row, column=column).value)
            if value is None:
                empty_cells.append((sheet_row, column_index))
            cells.append(value)
        rows.append(RawTableRow(label=f"row {sheet_row} of {table_label}", cells=cells))

    uncached_formula_columns = _uncached_formula_columns(
        raw_bytes=raw_bytes, sheet_title=worksheet.title, min_col=min_col, empty_cells=empty_cells, subject=subject
    )
    return RawTable(header=header, rows=rows, uncached_formula_columns=uncached_formula_columns)


def _missing_openpyxl() -> MissingDependencyError:
    return MissingDependencyError(
        dependency_name="openpyxl",
        extra_name=TABULAR_EXTRA,
        message="openpyxl is required to read Excel workbooks (.xlsx).",
    )


def _load_workbook(*, raw_bytes: bytes, data_only: bool, subject: str) -> "Workbook":
    """Open a workbook's bytes, wrapping what openpyxl raises on a file it cannot open as `CsvReadError`."""
    if openpyxl is None or InvalidFileException is None:
        raise _missing_openpyxl()
    try:
        return openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=data_only)
    # openpyxl raises these on a file that is not a workbook: a zip it cannot open, a zip missing a part it needs, or a part
    # it cannot parse. None of their texts is quoted, since they can carry the file's own content.
    except (zipfile.BadZipFile, InvalidFileException, KeyError, ValueError, OSError) as exc:
        msg = f"Could not open {subject} as an Excel workbook (.xlsx): {type(exc).__name__}"
        raise CsvReadError(msg) from exc


def _choose_table(*, workbook: "Workbook", table_name: str | None, subject: str) -> tuple["Worksheet", "Table"]:
    """The Table to read and its worksheet: the one named, compared ignoring case, or the workbook's only Table."""
    found: list[tuple[Worksheet, Table]] = []
    # A workbook opened neither read-only nor write-only lists its sheets of cells as `Worksheet`s; a chart sheet, which
    # holds no cells and so no Table, is not among them.
    for sheet in workbook.worksheets:
        worksheet = cast("Worksheet", sheet)
        found.extend((worksheet, table) for table in worksheet.tables.values())
    found_names = ", ".join(f"'{table.displayName}'" for _, table in found) or "none"
    if table_name is not None:
        wanted = table_name.casefold()
        for found_worksheet, found_table in found:
            if found_table.displayName.casefold() == wanted or (found_table.name or "").casefold() == wanted:
                return found_worksheet, found_table
        msg = f"{subject.capitalize()} holds no Table named '{table_name}'; the Tables it holds: {found_names}."
        raise TableSelectionError(msg)
    if len(found) == 1:
        return found[0]
    if not found:
        msg = f"{subject.capitalize()} holds no Excel Table: define the rows to read as a Table (Insert > Table) in the workbook."
        raise TableSelectionError(msg)
    msg = f"{subject.capitalize()} holds several Tables ({found_names}) and the step names none: name the Table to read with `table`."
    raise TableSelectionError(msg)


def _uncached_formula_columns(
    *, raw_bytes: bytes, sheet_title: str, min_col: int, empty_cells: list[tuple[int, int]], subject: str
) -> frozenset[int]:
    """The columns, by 0-based index in the Table, of the empty cells that hold a formula: formulas with no cached value.

    The workbook is opened a second time, keeping its formulas, only when some cell read empty.
    """
    if not empty_cells:
        return frozenset()
    formula_worksheet = _load_workbook(raw_bytes=raw_bytes, data_only=False, subject=subject)[sheet_title]
    columns: set[int] = set()
    for sheet_row, column_index in empty_cells:
        if formula_worksheet.cell(row=sheet_row, column=min_col + column_index).data_type == "f":
            columns.add(column_index)
    return frozenset(columns)


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
