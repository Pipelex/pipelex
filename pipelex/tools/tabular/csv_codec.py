"""CSV codec — the I/O bridge between CSV files and ``ListContent[row-concept]``.

CSV is an I/O codec, not a prompt-render format: it does NOT join the
``rendered_plain/markdown/html/json`` ``TextFormat`` router. This module owns row read/write
(``read_rows``/``write_rows``), the shared flatness/field-order helper (``flat_field_names``,
used by BOTH read and write, and by the Excel reader), the CSV half of reading a table
(``read_csv_raw_table``, which ``pipelex.tools.tabular.table_reader`` calls for a ``PipeStructure``
step), the run-input binding (``list_content_from_csv``), the write binding
(``csv_from_list_content``), and the write seam (``assert_supported_table_suffix``). Matching the
header to the row concept's fields and binding the rows to it are format-neutral, in
``pipelex.tools.tabular.table_records``, so a row concept that reads a ``.csv`` reads a ``.xlsx``.

Dialect contract: the stdlib default ``QUOTE_MINIMAL`` quoting is the codec's wire
format — a value is quoted only when it contains the delimiter, the quote char, or a
newline. The exact-line write assertions in the test suite rely on this.
"""

import csv
import io
import types
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

from mthds.protocol.problem.registry import CoreCode

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent, StuffContentType
from pipelex.tools.tabular.exceptions import (
    CsvColumnError,
    CsvError,
    CsvFlatnessError,
    CsvReadError,
)
from pipelex.tools.tabular.table_records import (
    RawTable,
    RawTableRow,
    TableBinding,
    TableCellValue,
    TableFormat,
    build_table_records,
    list_content_from_table_records,
)

# v1 dialect defaults. Configurable via codec params, never auto-guessed (design §9).
# The user-facing config surface (toml default / --delimiter / --encoding flags) is a
# deferred follow-up — v1 exposes delimiter/encoding only as function params.
DEFAULT_DELIMITER = ","
DEFAULT_ENCODING = "utf-8"
# Read with utf-8-sig so a UTF-8 BOM is transparently stripped — Excel's "CSV UTF-8" export always
# prepends one, and the headline use case is round-tripping Excel files. utf-8-sig reads plain UTF-8
# unchanged when no BOM is present. Writes stay on plain utf-8 (utf-8-sig would prepend a BOM).
DEFAULT_READ_ENCODING = "utf-8-sig"

_NONE_TYPE = type(None)
_UnionType = getattr(types, "UnionType", None)  # Py3.10+: types.UnionType (PEP 604 `X | None`)
# Scalar python types a CSV cell can round-trip. `bool` precedes `int` semantically
# (bool is an int subclass) but membership here is by identity, so both are accepted.
_FLAT_SCALAR_TYPES: frozenset[type] = frozenset({str, int, float, bool, date, datetime})


# ---------------------------------------------------------------------------------------
# Flatness classifier (shared by read AND write)
# ---------------------------------------------------------------------------------------


def _is_flat_annotation(annotation: Any) -> bool:
    """Return whether a pydantic field annotation is a CSV-flat scalar.

    Unwraps ``Optional`` (a single non-``None`` arm); ACCEPTS the scalar python types,
    ``Literal[...]`` and ``Enum`` (choice-constrained) scalars; REJECTS genuine unions,
    containers, nested models, and ``Any``.
    """
    origin = get_origin(annotation)
    if origin in {Union, _UnionType}:
        non_none_args = [arg for arg in get_args(annotation) if arg is not _NONE_TYPE]
        if len(non_none_args) != 1:
            # A genuine multi-type union (e.g. int | str) is not flat.
            return False
        return _is_flat_annotation(non_none_args[0])
    if origin is Literal:
        # Only string-valued choices round-trip through a CSV cell: the codec writes the value as a
        # bare string and pydantic does not coerce that string back into a non-string Literal member.
        return all(isinstance(arg, str) for arg in get_args(annotation))
    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            # Same reason: only a str-valued Enum (e.g. StrEnum) round-trips; an IntEnum would not.
            return all(isinstance(member.value, str) for member in annotation)
        return annotation in _FLAT_SCALAR_TYPES
    return False


def flat_field_names(row_model: type[StuffContent]) -> list[str]:
    """Validate that ``row_model`` is CSV-flat and return its field names in declared order.

    The single shared flatness classifier used by BOTH read and write. Unwraps
    ``Optional``; ACCEPTS ``str``/``int``/``float``/``bool``/``datetime.date`` and
    ``Literal``/choice-constrained scalars; REJECTS list/dict/nested/concept-typed/
    ``Union``/``Any`` fields with a ``CsvFlatnessError`` naming the offending field.
    """
    field_names: list[str] = []
    for field_name, field_info in row_model.model_fields.items():
        if not _is_flat_annotation(field_info.annotation):
            msg = (
                f"Concept {row_model.__name__!r} is not CSV-flat: field {field_name!r} has type "
                f"{field_info.annotation!r}, but CSV rows accept scalar fields only "
                f"(text/integer/number/boolean/date, optionals, and Literal/choice-constrained scalars). "
                f"Project to a flat concept first."
            )
            raise CsvFlatnessError(msg)
        field_names.append(field_name)
    return field_names


# ---------------------------------------------------------------------------------------
# read_rows / write_rows primitives
# ---------------------------------------------------------------------------------------


def _assert_single_char_delimiter(delimiter: str) -> None:
    """Reject a delimiter the stdlib ``csv`` module cannot use.

    ``csv`` requires the delimiter to be exactly one character and additionally rejects the
    newline characters (LF/CR) and the quote character ``"`` (it collides with the default
    quotechar) — each passes the length check but makes ``csv.reader``/``csv.writer`` raise a raw
    ``ValueError``/``TypeError`` at construction. Validating them up front keeps the codec's
    typed-error boundary intact so no raw exception escapes for the exposed ``delimiter`` parameter.
    """
    if len(delimiter) != 1:
        msg = f"CSV delimiter must be a single character, got {delimiter!r}."
        raise CsvError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
    if delimiter in {"\n", "\r"}:
        msg = f"CSV delimiter cannot be a newline character, got {delimiter!r}."
        raise CsvError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
    if delimiter == '"':
        # The default quote character; csv raises "bad delimiter or quotechar value" if they collide.
        msg = f"CSV delimiter cannot be the quote character, got {delimiter!r}."
        raise CsvError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)


def csv_subject(*, input_name: str | None) -> str:
    """How a message names the file it refuses: by the input it was given as, never by its path, which is the caller's."""
    return f"the CSV file given for input '{input_name}'" if input_name is not None else "the CSV file"


def _validate_header(header: list[str], *, subject: str) -> None:
    """Reject an empty header, or a header with a blank or duplicate column.

    A header cell is the file's own text, which no message quotes: a column is named by its 1-based position.
    """
    if not header:
        # An empty first row (a leading blank line, or a file that is just a newline) names no
        # columns; treat it as a malformed header rather than letting it surface as a confusing
        # "row wider than header" / missing-required error downstream.
        msg = f"Found an empty header row in {subject}; a header naming the columns is required."
        raise CsvColumnError(msg)
    seen: set[str] = set()
    for column_number, column in enumerate(header, start=1):
        if not column.strip():
            msg = f"Found a blank header cell in column {column_number} of {subject}; every column needs a non-empty name."
            raise CsvColumnError(msg)
        if column in seen:
            msg = f"Column {column_number} of {subject} repeats the name of an earlier column; column names must be unique."
            raise CsvColumnError(msg)
        seen.add(column)


def _read_csv_bytes(*, path: Path, subject: str) -> bytes:
    """Read a CSV file's bytes, wrapping an ``OSError`` as ``CsvReadError`` written by its reason alone, never its path."""
    try:
        return path.read_bytes()
    except OSError as exc:
        msg = f"Could not read {subject}: {exc.strerror or type(exc).__name__}"
        raise CsvReadError(msg) from exc


def _parse_csv_rows(*, raw_bytes: bytes, delimiter: str, encoding: str, subject: str) -> list[tuple[int, list[str]]]:
    """Decode and parse a CSV file's bytes into its records, each with its 1-based physical line number.

    Each record carries ``reader.line_num`` (the count of physical lines consumed so far) rather than an enumeration, so
    a quoted cell spanning several physical lines does not skew the line numbers of the records that follow it. The
    reader runs in ``strict=True`` mode so malformed quoting raises ``csv.Error`` at the boundary rather than silently
    merging the following lines into one cell. Wraps every raw ``UnicodeDecodeError``/``LookupError``/``csv.Error`` as
    ``CsvReadError``: a decoding error's own text quotes the byte it refused, so it is written by its reason alone.
    """
    _assert_single_char_delimiter(delimiter)
    try:
        text = raw_bytes.decode(encoding)
    except UnicodeDecodeError as exc:
        msg = f"Could not decode {subject} as {encoding}: {exc.reason}"
        raise CsvReadError(msg) from exc
    except LookupError as exc:
        msg = f"Unknown encoding {encoding!r} for {subject}"
        raise CsvReadError(msg) from exc
    numbered_rows: list[tuple[int, list[str]]] = []
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        for row in reader:
            numbered_rows.append((reader.line_num, row))
    except csv.Error as exc:
        # The csv module's own wording, which names the dialect's characters and never a cell.
        msg = f"Malformed CSV in {subject}: {exc}"
        raise CsvReadError(msg) from exc
    return numbered_rows


def _split_table(
    *, numbered_rows: list[tuple[int, list[str]]], subject: str, is_strict_header: bool
) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Split a CSV file's records into a validated header row and the (1-based-line-numbered) data rows.

    Blank physical lines (which ``csv`` yields as ``[]``) are skipped, matching ``csv.DictReader``; a data row wider
    than the header is rejected (its surplus cells map to no column). The header must name columns; a strict header,
    which every column must match a field, also refuses a blank or repeated header cell.
    """
    if not numbered_rows:
        msg = f"Found nothing in {subject}; a header row is required."
        raise CsvReadError(msg)

    header = numbered_rows[0][1]
    if is_strict_header:
        _validate_header(header, subject=subject)
    elif not header:
        msg = f"Found an empty header row in {subject}; a header naming the columns is required."
        raise CsvColumnError(msg)

    data_rows: list[tuple[int, list[str]]] = []
    for line_number, row in numbered_rows[1:]:
        if not row:
            # Blank physical line (csv yields []). Skip it; a single empty cell is [''] and is kept.
            continue
        if len(row) > len(header):
            msg = (
                f"Row {line_number} of {subject} has {len(row)} fields but the header declares "
                f"{len(header)} column(s); the surplus cells map to no column."
            )
            raise CsvColumnError(msg)
        data_rows.append((line_number, row))
    return header, data_rows


def _read_table(path: Path, *, delimiter: str, encoding: str, subject: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Read a CSV file into a strictly validated header row + the (1-based-line-numbered) data rows.

    No message names the file's path, which the caller gave, nor quotes its content. ``subject`` names the file as the
    input it was given as, when that is known.
    """
    raw_bytes = _read_csv_bytes(path=path, subject=subject)
    numbered_rows = _parse_csv_rows(raw_bytes=raw_bytes, delimiter=delimiter, encoding=encoding, subject=subject)
    return _split_table(numbered_rows=numbered_rows, subject=subject, is_strict_header=True)


def read_csv_raw_table(*, raw_bytes: bytes, binding: TableBinding, subject: str) -> RawTable:
    """Read a CSV file's bytes into a `RawTable`: comma-separated UTF-8, a leading byte order mark ignored.

    A row is named by its physical line, as an editor shows it. Under a binding that refuses a column matching no
    field, the header is validated strictly, as a run input's always was: no blank and no repeated header cell.

    Raises:
        CsvReadError: The bytes do not decode or do not parse, or the file is empty.
        CsvColumnError: The header is empty or, strictly validated, holds a blank or repeated cell, or a row is wider
            than the header.
    """
    numbered_rows = _parse_csv_rows(raw_bytes=raw_bytes, delimiter=DEFAULT_DELIMITER, encoding=DEFAULT_READ_ENCODING, subject=subject)
    header, data_rows = _split_table(numbered_rows=numbered_rows, subject=subject, is_strict_header=binding.refuses_unmatched_columns)
    raw_rows = [RawTableRow(label=f"row {line_number}", cells=list[TableCellValue](row)) for line_number, row in data_rows]
    return RawTable(header=header, rows=raw_rows)


def _row_to_dict(data_row: list[str], *, header: list[str]) -> dict[str, str]:
    """Map a raw data row onto the header, padding a short row with empty cells."""
    return {column: (data_row[index] if index < len(data_row) else "") for index, column in enumerate(header)}


def read_rows(path: Path, *, delimiter: str = DEFAULT_DELIMITER, encoding: str = DEFAULT_READ_ENCODING) -> list[dict[str, str]]:
    """Read a CSV file into a list of header-keyed string rows.

    A header row is required; blank lines are skipped. Raises ``CsvReadError`` for a
    missing/unreadable file, an unknown/wrong encoding, or malformed quoting; raises
    ``CsvColumnError`` for a duplicate/blank header cell or a data row wider than the header.
    """
    header, data_rows = _read_table(path, delimiter=delimiter, encoding=encoding, subject=csv_subject(input_name=None))
    return [_row_to_dict(row, header=header) for _, row in data_rows]


def write_rows(
    *,
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    delimiter: str = DEFAULT_DELIMITER,
    encoding: str = DEFAULT_ENCODING,
) -> None:
    """Write header-keyed string rows to a CSV file, emitting ``headers`` in order.

    An empty ``rows`` still writes the header line. Raises ``CsvError`` if the delimiter
    is invalid, the encoding is unknown, a cell is not encodable in ``encoding``, or the
    file cannot be written.
    """
    _assert_single_char_delimiter(delimiter)
    try:
        with path.open("w", encoding=encoding, newline="") as csv_file:
            writer = csv.writer(csv_file, delimiter=delimiter)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row.get(column, "") for column in headers])
    # The path is the one the caller asked to write; the rows are the run's output, so no message quotes a cell, which
    # an encoding error's own text does, nor repeats the path, which an `OSError`'s does.
    except LookupError as exc:
        msg = f"Unknown encoding {encoding!r} for CSV file {path}"
        raise CsvError(msg).with_error_code(CoreCode.REQUEST_INVALID) from exc
    except UnicodeEncodeError as exc:
        msg = f"Could not encode CSV file {path} as {encoding}: a cell holds a character {encoding} cannot write ({exc.reason})"
        raise CsvError(msg).with_error_code(CoreCode.REQUEST_INVALID) from exc
    except OSError as exc:
        msg = f"Could not write CSV file {path}: {exc.strerror or type(exc).__name__}"
        raise CsvError(msg).with_error_code(CoreCode.REQUEST_INVALID) from exc


# ---------------------------------------------------------------------------------------
# Format seam
# ---------------------------------------------------------------------------------------

# Suffixes the tabular codec claims: the .csv built-in and the .xlsx workbook the optional `tabular` extra reads.
_TABULAR_SUFFIXES: frozenset[str] = frozenset({".csv", ".xlsx"})


def is_tabular_path(path: Path) -> bool:
    """Whether ``path``'s suffix is one the tabular codec claims: ``.csv`` or ``.xlsx``.

    The input hook uses this to decide whether a ``{"url": ...}`` reference is a table to read rather than an ordinary
    record dict.
    """
    return path.suffix.lower() in _TABULAR_SUFFIXES


def assert_supported_table_suffix(path: Path) -> None:
    """Format seam of a table the CLI writes: accept ``.csv``; reject everything else.

    Only reading reaches Excel workbooks: a ``.xlsx`` path raises ``CsvError`` saying so, and any other suffix raises a
    generic unsupported-format ``CsvError``.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return
    # The file's name is the caller's own text, which no message carries: its suffix names the format.
    if suffix == ".xlsx":
        msg = "Writing Excel files (.xlsx) is not supported: write a .csv file, which Excel opens."
        raise CsvError(msg)
    msg = f"Unsupported table file format: only .csv is supported (got suffix {path.suffix!r})."
    raise CsvError(msg)


# ---------------------------------------------------------------------------------------
# Concept binding
# ---------------------------------------------------------------------------------------


def list_content_from_csv(
    path: Path,
    *,
    row_model: type[StuffContentType],
    delimiter: str = DEFAULT_DELIMITER,
    encoding: str = DEFAULT_READ_ENCODING,
    input_name: str | None = None,
) -> ListContent[StuffContentType]:
    """Read a CSV file given as a run input into a ``ListContent`` of ``row_model`` instances (one row → one item).

    The run input's binding (``TableBinding.RUN_INPUT``): every column must match a field of ``row_model``, compared
    as `pipelex.cogt.doc_gen.header_matching` compares a header and a field, so an extra column or a missing *required*
    column raises ``CsvColumnError``; a missing *optional* column sets that field to ``None`` for all rows, or leaves a
    defaulted field that refuses ``None`` to its default. Empty cells map to ``None`` BEFORE pydantic validation (so
    they must target optional fields), but are left out for a defaulted field that refuses ``None``, which then takes
    its default; remaining strings are coerced via pydantic's lax validation. A coercion failure raises
    ``CsvCoercionError`` naming the 1-based row and the field. ``row_model`` must be CSV-flat (see ``flat_field_names``).

    The file is the caller's input: no message names its path, quotes a cell, or names a column the concept does not
    declare, which is the file's own text: a message names the file by ``input_name``, the input it was given as, when
    the caller knows it.
    """
    assert_supported_table_suffix(path)
    field_names = flat_field_names(row_model)
    subject = csv_subject(input_name=input_name)
    header, data_rows = _read_table(path, delimiter=delimiter, encoding=encoding, subject=subject)
    raw_table = RawTable(
        header=header,
        rows=[RawTableRow(label=f"row {line_number}", cells=list[TableCellValue](row)) for line_number, row in data_rows],
    )
    table_records = build_table_records(
        raw_table=raw_table,
        table_format=TableFormat.CSV,
        field_names=field_names,
        row_field=None,
        binding=TableBinding.RUN_INPUT,
        subject=subject,
    )
    return list_content_from_table_records(
        table_records=table_records, row_model=row_model, row_field=None, binding=TableBinding.RUN_INPUT, subject=subject
    )


def csv_from_list_content(
    list_content: ListContent[StuffContentType],
    *,
    row_model: type[StuffContentType],
    path: Path,
    delimiter: str = DEFAULT_DELIMITER,
    encoding: str = DEFAULT_ENCODING,
) -> None:
    """Write a flat ``ListContent`` to a CSV file, one row per item.

    Columns are ``row_model``'s scalar fields in declared order — derived from the
    DECLARED model, never from ``list_content.items[0]`` — so an empty list still writes
    a correct header-only file. Each item is serialized via ``model_dump(mode="json")``;
    ``None`` maps to an empty cell (never the string ``"None"``). ``row_model`` must be
    CSV-flat (see ``flat_field_names``).
    """
    assert_supported_table_suffix(path)
    headers = flat_field_names(row_model)
    rows: list[dict[str, str]] = []
    for item_index, item in enumerate(list_content.items):
        if not isinstance(item, row_model):
            msg = f"Cannot write CSV: item {item_index} is a {type(item).__name__}, not the declared row model {row_model.__name__!r}."
            raise CsvError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
        dumped = item.model_dump(mode="json")
        rows.append({field_name: _to_cell(dumped.get(field_name)) for field_name in headers})
    write_rows(path=path, headers=headers, rows=rows, delimiter=delimiter, encoding=encoding)


def _to_cell(value: Any) -> str:
    """Serialize one ``model_dump(mode="json")`` scalar to a CSV cell.

    ``None`` becomes an empty cell (never ``"None"``); booleans become lowercase
    ``true``/``false`` (round-trip-safe under pydantic's lax bool coercion).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
