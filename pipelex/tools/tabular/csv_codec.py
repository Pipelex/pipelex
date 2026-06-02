"""CSV codec — the I/O bridge between CSV files and ``ListContent[row-concept]``.

CSV is an I/O codec, not a prompt-render format: it does NOT join the
``rendered_plain/markdown/html/json`` ``TextFormat`` router. This single module owns
row read/write (``read_rows``/``write_rows``), the shared flatness/field-order helper
(``flat_field_names``, used by BOTH read and write), the concept binding
(``list_content_from_csv``/``csv_from_list_content``), and a thin format seam
(``assert_supported_table_suffix``) so an ``openpyxl``-backed ``.xlsx`` codec can be
added later under ``pipelex[tabular]`` without touching callers.

Dialect contract: the stdlib default ``QUOTE_MINIMAL`` quoting is the codec's wire
format — a value is quoted only when it contains the delimiter, the quote char, or a
newline. The exact-line write assertions in the test suite rely on this.
"""

import csv
import types
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from pydantic import ValidationError

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent, StuffContentType
from pipelex.tools.tabular.exceptions import (
    CsvCoercionError,
    CsvColumnError,
    CsvError,
    CsvFlatnessError,
    CsvReadError,
)

if TYPE_CHECKING:
    from pydantic_core import ErrorDetails

# v1 dialect defaults. Configurable via codec params, never auto-guessed (design §9).
# The user-facing config surface (toml default / --delimiter / --encoding flags) is a
# deferred follow-up — v1 exposes delimiter/encoding only as function params.
DEFAULT_DELIMITER = ","
DEFAULT_ENCODING = "utf-8"

_NONE_TYPE = type(None)
_UNION_TYPE = getattr(types, "UnionType", None)  # Py3.10+: types.UnionType (PEP 604 `X | None`)
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
    if origin in {Union, _UNION_TYPE}:
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


def _annotation_allows_none(annotation: Any) -> bool:
    """Whether a field annotation accepts ``None`` (an ``Optional`` / ``... | None`` field)."""
    if get_origin(annotation) in {Union, _UNION_TYPE}:
        return any(arg is _NONE_TYPE for arg in get_args(annotation))
    return annotation is _NONE_TYPE


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
        raise CsvError(msg)
    if delimiter in {"\n", "\r"}:
        msg = f"CSV delimiter cannot be a newline character, got {delimiter!r}."
        raise CsvError(msg)
    if delimiter == '"':
        # The default quote character; csv raises "bad delimiter or quotechar value" if they collide.
        msg = f"CSV delimiter cannot be the quote character, got {delimiter!r}."
        raise CsvError(msg)


def _validate_header(header: list[str], path: Path) -> None:
    """Reject a CSV header with a blank or duplicate column."""
    seen: set[str] = set()
    for column in header:
        if not column.strip():
            msg = f"CSV file {path} has a blank header cell; every column needs a non-empty name."
            raise CsvColumnError(msg)
        if column in seen:
            msg = f"CSV file {path} has a duplicate header column {column!r}; column names must be unique."
            raise CsvColumnError(msg)
        seen.add(column)


def _read_table(path: Path, *, delimiter: str, encoding: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Read a CSV file into a validated header row + the (1-based-line-numbered) data rows.

    The shared reader behind ``read_rows`` and ``list_content_from_csv`` — keeps the
    header explicit so column validation works even for a header-only file. Blank physical
    lines (which ``csv`` yields as ``[]``) are skipped, matching ``csv.DictReader``; a data
    row wider than the header is rejected (its surplus cells map to no column). Each kept row
    carries its 1-based physical CSV line number (the header is line 1, so the first data row
    is line 2, and skipped blank lines still advance the count) so error messages point at the
    line the author sees in their editor. The reader runs in ``strict=True`` mode so malformed
    quoting (e.g. an unterminated quoted field) raises ``csv.Error`` at the boundary rather than
    silently merging the following lines into one cell. Wraps every raw
    ``OSError``/``UnicodeDecodeError``/``LookupError``/``csv.Error`` as ``CsvReadError``.
    """
    _assert_single_char_delimiter(delimiter)
    # Capture each record's physical line number from ``reader.line_num`` (the count of physical lines
    # consumed so far) rather than enumerating, so a quoted cell that spans multiple physical lines
    # doesn't skew the line numbers of the records that follow it.
    numbered_rows: list[tuple[int, list[str]]] = []
    try:
        with path.open("r", encoding=encoding, newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=delimiter, strict=True)
            for row in reader:
                numbered_rows.append((reader.line_num, row))
    except UnicodeDecodeError as exc:
        msg = f"Could not decode CSV file {path} as {encoding}: {exc}"
        raise CsvReadError(msg) from exc
    except LookupError as exc:
        msg = f"Unknown encoding {encoding!r} for CSV file {path}: {exc}"
        raise CsvReadError(msg) from exc
    except csv.Error as exc:
        msg = f"Malformed CSV file {path}: {exc}"
        raise CsvReadError(msg) from exc
    except OSError as exc:
        msg = f"Could not read CSV file {path}: {exc}"
        raise CsvReadError(msg) from exc

    if not numbered_rows:
        msg = f"CSV file {path} is empty; a header row is required."
        raise CsvReadError(msg)

    header = numbered_rows[0][1]
    _validate_header(header, path)

    data_rows: list[tuple[int, list[str]]] = []
    for line_number, row in numbered_rows[1:]:
        if not row:
            # Blank physical line (csv yields []). Skip it; a single empty cell is [''] and is kept.
            continue
        if len(row) > len(header):
            msg = (
                f"CSV file {path} row {line_number} has {len(row)} fields but the header declares "
                f"{len(header)} column(s); the surplus cells map to no column."
            )
            raise CsvColumnError(msg)
        data_rows.append((line_number, row))
    return header, data_rows


def _row_to_dict(header: list[str], data_row: list[str]) -> dict[str, str]:
    """Map a raw data row onto the header, padding a short row with empty cells."""
    return {column: (data_row[index] if index < len(data_row) else "") for index, column in enumerate(header)}


def read_rows(path: Path, *, delimiter: str = DEFAULT_DELIMITER, encoding: str = DEFAULT_ENCODING) -> list[dict[str, str]]:
    """Read a CSV file into a list of header-keyed string rows.

    A header row is required; blank lines are skipped. Raises ``CsvReadError`` for a
    missing/unreadable file, an unknown/wrong encoding, or malformed quoting; raises
    ``CsvColumnError`` for a duplicate/blank header cell or a data row wider than the header.
    """
    header, data_rows = _read_table(path, delimiter=delimiter, encoding=encoding)
    return [_row_to_dict(header, row) for _, row in data_rows]


def write_rows(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    *,
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
    except LookupError as exc:
        msg = f"Unknown encoding {encoding!r} for CSV file {path}: {exc}"
        raise CsvError(msg) from exc
    except UnicodeEncodeError as exc:
        msg = f"Could not encode CSV file {path} as {encoding}: {exc}"
        raise CsvError(msg) from exc
    except OSError as exc:
        msg = f"Could not write CSV file {path}: {exc}"
        raise CsvError(msg) from exc


# ---------------------------------------------------------------------------------------
# Format seam
# ---------------------------------------------------------------------------------------

# Suffixes the tabular codec claims: the .csv built-in plus the deferred .xlsx seam.
_TABULAR_SUFFIXES: frozenset[str] = frozenset({".csv", ".xlsx"})


def is_tabular_path(path: Path) -> bool:
    """Whether ``path``'s suffix is one the tabular codec claims.

    ``True`` for ``.csv`` (the v1 built-in) and ``.xlsx`` (the deferred seam). The input
    hook uses this to decide whether a ``{"url": ...}`` reference is a table to read rather
    than an ordinary record dict. ``.xlsx`` is claimed here so it reaches the codec's clear
    "needs pipelex[tabular]" seam error (via ``assert_supported_table_suffix``) instead of
    being misread as a record.
    """
    return path.suffix.lower() in _TABULAR_SUFFIXES


def assert_supported_table_suffix(path: Path) -> None:
    """Format seam: accept ``.csv`` (the only v1 built-in); reject everything else.

    A ``.xlsx`` path raises ``CsvError`` pointing at the optional ``pipelex[tabular]``
    extra; any other suffix raises a generic unsupported-format ``CsvError``. This is
    the seam an ``openpyxl``-backed codec slots into later without touching callers.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return
    if suffix == ".xlsx":
        msg = (
            f"Reading/writing Excel files ({path.name}) requires the optional 'pipelex[tabular]' extra, "
            f"which is not part of v1. Convert to .csv, or install 'pipelex[tabular]' once it ships."
        )
        raise CsvError(msg)
    msg = f"Unsupported table file format for {path.name!r}: only .csv is supported (got suffix {path.suffix!r})."
    raise CsvError(msg)


# ---------------------------------------------------------------------------------------
# Concept binding
# ---------------------------------------------------------------------------------------


def list_content_from_csv(
    path: Path,
    row_model: type[StuffContentType],
    *,
    delimiter: str = DEFAULT_DELIMITER,
    encoding: str = DEFAULT_ENCODING,
) -> ListContent[StuffContentType]:
    """Read a CSV file into a ``ListContent`` of ``row_model`` instances (one row → one item).

    Columns must match ``row_model``'s field names (no implicit remap): an extra column
    or a missing *required* column raises ``CsvColumnError``; a missing *optional* column
    sets that field to ``None`` for all rows. Empty cells map to ``None`` BEFORE pydantic
    validation (so they must target optional fields); remaining strings are coerced via
    pydantic's lax validation. A coercion failure raises ``CsvCoercionError`` naming the
    1-based row/column and field. ``row_model`` must be CSV-flat (see ``flat_field_names``).
    """
    assert_supported_table_suffix(path)
    field_names = flat_field_names(row_model)
    field_name_set = set(field_names)
    required_fields = {name for name, field_info in row_model.model_fields.items() if field_info.is_required()}

    header, data_rows = _read_table(path, delimiter=delimiter, encoding=encoding)
    header_set = set(header)

    extra_columns = header_set - field_name_set
    if extra_columns:
        msg = (
            f"CSV file {path} has column(s) {sorted(extra_columns)} not declared on concept {row_model.__name__!r}. "
            f"Remove them or project to a matching flat concept."
        )
        raise CsvColumnError(msg)

    missing_required = required_fields - header_set
    if missing_required:
        msg = f"CSV file {path} is missing required column(s) {sorted(missing_required)} for concept {row_model.__name__!r}."
        raise CsvColumnError(msg)

    # A CSV that omits a *nullable* column means "no value" for every row → None (CT2), regardless of
    # the row model's own default. Carrying these as explicit None keeps the contract from silently
    # depending on a non-None field default (e.g. ``nickname: str | None = "anon"`` → None, not "anon").
    # A non-nullable defaulted field (e.g. ``count: int = 0``) is left absent so its own default
    # applies — forcing None there would fail validation, not honor the column's absence.
    omitted_nullable_fields = {name for name in (field_name_set - header_set) if _annotation_allows_none(row_model.model_fields[name].annotation)}

    items: list[StuffContentType] = []
    for row_number, data_row in data_rows:
        cell_map = _row_to_dict(header, data_row)
        # Empty cell -> None BEFORE validation (so it targets an optional field, or fails required).
        row_data: dict[str, str | None] = {column: (value or None) for column, value in cell_map.items()}
        for omitted_field in omitted_nullable_fields:
            row_data[omitted_field] = None
        try:
            item = row_model.model_validate(row_data)
        except ValidationError as exc:
            error_fields = sorted({_validation_error_label(error) for error in exc.errors()})
            fields_label = ", ".join(error_fields) or "?"
            msg = f"Could not coerce CSV row {row_number} of {path} for concept {row_model.__name__!r}: field(s) {fields_label} — {exc}"
            raise CsvCoercionError(msg) from exc
        items.append(item)

    return ListContent(items=items)


def csv_from_list_content(
    list_content: ListContent[StuffContentType],
    row_model: type[StuffContentType],
    path: Path,
    *,
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
            raise CsvError(msg)
        dumped = item.model_dump(mode="json")
        rows.append({field_name: _to_cell(dumped.get(field_name)) for field_name in headers})
    write_rows(path, headers, rows, delimiter=delimiter, encoding=encoding)


def _validation_error_label(error: "ErrorDetails") -> str:
    """Best field label for one pydantic error: the dotted ``loc``, else the error type.

    A model-level failure (e.g. a ``model_validator``) has an empty ``loc``; falling back to
    the error type keeps the coercion message from naming an unhelpful ``field(s) ?``.
    """
    loc = error.get("loc") or ()
    if loc:
        return ".".join(str(part) for part in loc)
    return str(error.get("type", "model"))


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
