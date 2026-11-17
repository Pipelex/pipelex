"""The format-neutral half of reading a table into records: matching its columns to fields, and binding its rows to a row concept.

A table file is read in two steps, whatever its format:

1. **The codec** (`csv_codec` for a CSV file, `xlsx_codec` for an Excel workbook) reads the file into a `RawTable`: the
   header row, and each data row's cells, typed as the file gives them (a CSV cell is always text, a workbook cell is a
   number, a date, a boolean or a text).
2. **This module** matches the header to the row concept's fields (`build_table_records`), with the comparison
   `pipelex.cogt.doc_gen.header_matching` defines, the one a document engine's fill uses too, and binds the records to
   the row concept (`list_content_from_table_records`), converting each value to its field's type with pydantic's lax
   validation, so a row concept that reads a `.csv` reads a `.xlsx`.

The records between the two steps (`TableRecords`) are plain data, so a host runtime can read the file in one process,
an activity, and bind the records to the row concept in another, the step's. Each cell is tagged with the kind of value
it holds (`TableCell`), so the records survive any serialization exactly: a text that looks like a number or a date stays
a text, whatever converter carries them.

Two bindings exist (`TableBinding`), since a table reaches a run two ways:

- **A run input** (`RUN_INPUT`), a `{"url": "...csv"}` given for a structured list input: every column must match a field,
  and a nullable field no column matches reads as null.
- **A `PipeStructure` step** (`STEP`), reading a `Document`: a column that matches no field is ignored, and a field no
  column matches, or an empty cell, takes the field's default, null when it declares none, as the MTHDS standard rules.

No message names the file's path or quotes a cell, which are the caller's: a column is named by its position, or by the
field it matches, which the method declares.
"""

import math
import re
import types
from datetime import date, datetime, time
from enum import Enum, StrEnum
from typing import Annotated, Any, Final, Literal, NamedTuple, TypeAlias, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.cogt.doc_gen.header_matching import column_fields
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContentType
from pipelex.tools.tabular.exceptions import CsvCoercionError, CsvColumnError
from pipelex.tools.typing.annotation_utils import annotation_admits_none
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of, located_validation_errors, refusal_reason_without_input

# A cell's value, as a codec reads it: the text of a CSV cell, the typed value of a workbook's cell, or None when empty.
TableCellValue: TypeAlias = bool | int | float | datetime | date | str | None

# What a refusal of a table's file type names as the reader that cannot take it, in the place a model is named.
TABLE_READER: Final[str] = "table_reader"

_NONE_TYPE = type(None)
_UnionType = getattr(types, "UnionType", None)


class TableFormat(StrEnum):
    """The formats a table is read from."""

    CSV = "csv"
    XLSX = "xlsx"


class TableBinding(StrEnum):
    """Which rules bind a table to a row concept: a run input's, or a `PipeStructure` step's."""

    RUN_INPUT = "run_input"
    STEP = "step"

    @property
    def refuses_unmatched_columns(self) -> bool:
        """Whether a column whose header matches no field is refused, rather than ignored."""
        match self:
            case TableBinding.RUN_INPUT:
                return True
            case TableBinding.STEP:
                return False

    @property
    def names_its_region(self) -> bool:
        """Whether the reader can name the region of a workbook it reads, with `table` or `sheet_range`, as a step can."""
        match self:
            case TableBinding.RUN_INPUT:
                return False
            case TableBinding.STEP:
                return True

    @property
    def nulls_absent_nullable_fields(self) -> bool:
        """Whether a nullable field no column matches, or an empty cell under it, reads as null whatever its default."""
        match self:
            case TableBinding.RUN_INPUT:
                return True
            case TableBinding.STEP:
                return False


class RawTableRow(NamedTuple):
    """One data row of a table as its codec read it."""

    label: str
    """How a message names the row, as the author finds it in the file: `row 4` of a CSV file, by its line."""
    cells: list[TableCellValue]
    """The row's cells, in the header's order; a row shorter than the header lacks its trailing cells."""


class RawTable(NamedTuple):
    """A table as its codec read it, before its columns are matched to fields."""

    header: list[str]
    rows: list[RawTableRow]
    uncached_formula_columns: frozenset[int] = frozenset()
    """The 0-based indexes of the columns holding a formula with no cached value in some row, which read as empty."""


class CellKind(StrEnum):
    """The kinds of value a flat row field holds, which decide how a cell converts to it."""

    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"

    @property
    def is_text(self) -> bool:
        match self:
            case CellKind.TEXT:
                return True
            case CellKind.INTEGER | CellKind.NUMBER | CellKind.BOOLEAN | CellKind.DATE | CellKind.DATETIME:
                return False


class _TableCellBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TextCell(_TableCellBase):
    kind: Literal[CellKind.TEXT] = CellKind.TEXT
    value: str


class IntegerCell(_TableCellBase):
    kind: Literal[CellKind.INTEGER] = CellKind.INTEGER
    value: int


class NumberCell(_TableCellBase):
    kind: Literal[CellKind.NUMBER] = CellKind.NUMBER
    value: float


class BooleanCell(_TableCellBase):
    kind: Literal[CellKind.BOOLEAN] = CellKind.BOOLEAN
    value: bool


class DateCell(_TableCellBase):
    kind: Literal[CellKind.DATE] = CellKind.DATE
    value: date


class DatetimeCell(_TableCellBase):
    kind: Literal[CellKind.DATETIME] = CellKind.DATETIME
    value: datetime


# A non-empty cell of a record, tagged with the kind of value it holds. The tag is what keeps a cell exact across any
# serialization: a bare union would let a JSON validator read the text "00012" or "1700000000" as a datetime, and a host
# runtime's payload converter carries records between processes as JSON.
TableCell: TypeAlias = Annotated[
    TextCell | IntegerCell | NumberCell | BooleanCell | DateCell | DatetimeCell,
    Field(discriminator="kind"),
]


def table_cell_of(*, value: TableCellValue) -> TableCell | None:
    """A codec's cell value as a record's tagged cell, None for an empty cell."""
    # `bool` before `int`, which it subclasses, and `datetime` before `date`, which it subclasses.
    if value is None:
        return None
    if isinstance(value, bool):
        return BooleanCell(value=value)
    if isinstance(value, int):
        return IntegerCell(value=value)
    if isinstance(value, float):
        return NumberCell(value=value)
    if isinstance(value, datetime):
        return DatetimeCell(value=value)
    if isinstance(value, date):
        return DateCell(value=value)
    return TextCell(value=value)


class TableRecord(BaseModel):
    """One data row of a table, its values keyed by the field its column matched."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(description="How a message names the row, as the author finds it in the file")
    position: int = Field(description="The row's position among the table's data rows, counted from one")
    cells: dict[str, TableCell | None] = Field(
        default_factory=dict, description="The row's cells, by the field its column matched, each tagged with its kind; None when empty"
    )

    def plain_values(self) -> dict[str, TableCellValue]:
        """The row's values, by the field its column matched, untagged: None for an empty cell."""
        return {field_name: cell.value if cell is not None else None for field_name, cell in self.cells.items()}


class TableRecords(BaseModel):
    """A table read into records, plain data a host runtime carries from the process that read the file to the step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    table_format: TableFormat = Field(strict=False)
    matched_fields: list[str] = Field(default_factory=list, description="The fields a column matched, in the columns' order")
    records: list[TableRecord] = Field(default_factory=empty_list_factory_of(TableRecord))
    uncached_formula_fields: list[str] = Field(
        default_factory=list, description="The fields whose column holds a formula with no cached value, read as empty"
    )


def build_table_records(
    *,
    raw_table: RawTable,
    table_format: TableFormat,
    field_names: list[str],
    row_field: str | None,
    binding: TableBinding,
    subject: str,
) -> TableRecords:
    """Match a table's header to the fields and key each row's values by the field its column matched.

    Headers are compared with `column_fields`, a header spelling a field exactly binding it first. Refused: a header
    matching several fields, several headers matching one field, a header matching the field `row_field` names, and,
    under a binding that refuses them, a column matching no field. An empty cell, an empty text included, is None.

    Raises:
        CsvColumnError: The header does not match the fields as above.
    """
    headers = dict(enumerate(raw_table.header))
    matched_by_column = column_fields(headers=headers, field_names=field_names)

    unmatched_column_numbers = [column_index + 1 for column_index in headers if column_index not in matched_by_column]
    if unmatched_column_numbers and binding.refuses_unmatched_columns:
        msg = (
            f"Column(s) {', '.join(str(column_number) for column_number in unmatched_column_numbers)} of {subject} match no field "
            f"of the row concept, whose fields are {', '.join(field_names)}. Remove them or project to a matching flat concept."
        )
        raise CsvColumnError(msg)

    field_by_column: dict[int, str] = {}
    columns_by_field: dict[str, list[int]] = {}
    for column_index, matched_fields in matched_by_column.items():
        column_number = column_index + 1
        if len(matched_fields) > 1:
            msg = f"The header of column {column_number} of {subject} matches several fields of the row concept: {', '.join(matched_fields)}."
            raise CsvColumnError(msg).with_params(field=matched_fields[0])
        matched_field = matched_fields[0]
        if matched_field == row_field:
            msg = (
                f"The header of column {column_number} of {subject} matches the field '{row_field}', which receives each row's position: "
                "rename the column, or name another field as the row field."
            )
            raise CsvColumnError(msg).with_params(field=matched_field)
        field_by_column[column_index] = matched_field
        columns_by_field.setdefault(matched_field, []).append(column_number)
    for field_name, column_numbers in columns_by_field.items():
        if len(column_numbers) > 1:
            msg = f"The headers of columns {', '.join(str(number) for number in column_numbers)} of {subject} all match the field '{field_name}'."
            raise CsvColumnError(msg).with_params(field=field_name)

    records: list[TableRecord] = []
    for position, raw_row in enumerate(raw_table.rows, start=1):
        cells: dict[str, TableCell | None] = {}
        for column_index, field_name in field_by_column.items():
            cell = raw_row.cells[column_index] if column_index < len(raw_row.cells) else None
            cells[field_name] = table_cell_of(value=None if cell == "" else cell)
        records.append(TableRecord(label=raw_row.label, position=position, cells=cells))

    matched_fields = [field_by_column[column_index] for column_index in sorted(field_by_column)]
    uncached_formula_fields = [
        field_by_column[column_index] for column_index in sorted(raw_table.uncached_formula_columns) if column_index in field_by_column
    ]
    return TableRecords(
        table_format=table_format,
        matched_fields=matched_fields,
        records=records,
        uncached_formula_fields=uncached_formula_fields,
    )


def sentence_subject(*, subject: str) -> str:
    """A table file's subject opening a sentence: its first letter capitalized, the rest, the input's name included, as is.

    `str.capitalize` would lowercase the rest, renaming an input `Budget` to `budget` in the message.
    """
    return subject[:1].upper() + subject[1:]


def list_content_from_table_records(
    *,
    table_records: TableRecords,
    row_model: type[StuffContentType],
    row_field: str | None,
    binding: TableBinding,
    subject: str,
) -> ListContent[StuffContentType]:
    """Bind a table's records to the row concept, one item per record, converting each value to its field's type.

    ``row_model`` must be flat (``flat_field_names`` in ``csv_codec``), which the caller checks. ``row_field``, when
    given, receives each record's position.

    Under a step's binding, each value is converted by the rules of the MTHDS standard (`convert_cell`), stricter than
    pydantic's lax mode: a text gives an integer only from an integer literal, a number only from a decimal with a dot
    and no grouping, a date or a datetime only in ISO 8601, and a typed workbook cell keeps its kind, a boolean never
    reading as a number. Under a run input's binding, a value of a text field the file typed otherwise is read as its
    text, and every other value is converted by pydantic's lax validation, as a CSV input always was. The item is then
    validated against the row model either way, which checks choices and the model's own validators.

    Raises:
        CsvColumnError: A required field, other than the row field, has no column.
        CsvCoercionError: A value cannot be converted to its field's type, naming the row and the field.
    """
    present_fields = set(table_records.matched_fields)
    if row_field is not None:
        present_fields.add(row_field)
    required_fields = {name for name, field_info in row_model.model_fields.items() if field_info.is_required()}
    missing_required = sorted(required_fields - present_fields)
    if missing_required:
        msg = f"Required field(s) {missing_required} of concept {row_model.__name__!r} match no column of {subject}."
        raise CsvColumnError(msg).with_params(field=missing_required[0])

    # Under a run input's binding, a nullable field the table omits, or an empty cell under it, means "no value" → None,
    # regardless of the row model's own default. A non-nullable defaulted field is left out so its own default applies.
    # Under a step's binding, an absent value always leaves the field out, so it takes its default, None when it has none.
    nulled_fields: set[str] = set()
    if binding.nulls_absent_nullable_fields:
        nulled_fields = {name for name, field_info in row_model.model_fields.items() if annotation_admits_none(annotation=field_info.annotation)}
    field_kinds = {name: cell_kind_of(annotation=field_info.annotation) for name, field_info in row_model.model_fields.items()}

    items: list[StuffContentType] = []
    for record in table_records.records:
        row_name = record.label if binding.nulls_absent_nullable_fields else f"data row {record.position} ({record.label})"
        row_data: dict[str, Any] = {}
        for field_name in nulled_fields - present_fields:
            row_data[field_name] = None
        for field_name, value in record.plain_values().items():
            if value is None:
                if field_name in nulled_fields:
                    row_data[field_name] = None
                continue
            field_kind = field_kinds.get(field_name)
            match binding:
                case TableBinding.RUN_INPUT:
                    row_data[field_name] = _as_text(value=value) if field_kind is not None and field_kind.is_text else value
                case TableBinding.STEP:
                    if field_kind is None:
                        row_data[field_name] = value
                        continue
                    conversion = convert_cell(value=value, kind=field_kind)
                    if conversion.refusal is not None:
                        msg = f"Could not read {row_name} of {subject} for concept {row_model.__name__!r}: field {field_name} — {conversion.refusal}"
                        raise CsvCoercionError(msg).with_params(field=field_name)
                    row_data[field_name] = conversion.value
        if row_field is not None:
            row_data[row_field] = record.position
        try:
            item = row_model.model_validate(row_data)
        except ValidationError as exc:
            # The locations name what the row model's schema names, and a model-level failure, which has none, is named by
            # its error type. Each error's reason is given without the cell, which a validator's message can quote too.
            located_errors = located_validation_errors(validation_error=exc, validated_type=row_model)
            error_fields = sorted({located_error.location or located_error.error["type"] for located_error in located_errors})
            fields_label = ", ".join(error_fields) or "?"
            reasons = (
                "; ".join(sorted({refusal_reason_without_input(error=located_error.error) for located_error in located_errors})) or "invalid value"
            )
            msg = f"Could not coerce {row_name} of {subject} for concept {row_model.__name__!r}: field(s) {fields_label} — {reasons}"
            raise CsvCoercionError(msg).with_params(field=located_errors[0].location if located_errors else None) from exc
        items.append(item)
    return ListContent(items=items)


class CellConversion(NamedTuple):
    """A cell converted to its field's kind: the value, or why it could not be converted, never quoting the cell."""

    value: Any
    refusal: str | None = None


def cell_kind_of(*, annotation: Any) -> CellKind | None:
    """The kind of a flat field, optional or not: a text, choices among texts included, a number of either kind, a boolean or a date."""
    origin = get_origin(annotation)
    if origin in {Union, _UnionType}:
        non_none_args = [arg for arg in get_args(annotation) if arg is not _NONE_TYPE]
        return cell_kind_of(annotation=non_none_args[0]) if len(non_none_args) == 1 else None
    if origin is Literal:
        return CellKind.TEXT if all(isinstance(arg, str) for arg in get_args(annotation)) else None
    if not isinstance(annotation, type):
        return None
    if issubclass(annotation, Enum):
        return CellKind.TEXT if all(isinstance(member.value, str) for member in annotation) else None
    # `bool` before `int`, which it subclasses, and `datetime` before `date`, which it subclasses.
    for python_type, kind in (
        (str, CellKind.TEXT),
        (bool, CellKind.BOOLEAN),
        (int, CellKind.INTEGER),
        (float, CellKind.NUMBER),
        (datetime, CellKind.DATETIME),
        (date, CellKind.DATE),
    ):
        if annotation is python_type:
            return kind
    return None


# The standard's literal forms are written in ASCII digits: `re.ASCII` keeps `\d` from matching another script's digits,
# which `int` and `float` would otherwise read.
_INTEGER_LITERAL = re.compile(r"[+-]?\d+", re.ASCII)
_DECIMAL_LITERAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
# A typed cell holding an infinity or a NaN, and a decimal text whose exponent passes what a float holds.
_NOT_FINITE_REFUSAL: Final[str] = "the cell holds a number that is not finite"
_TOO_LARGE_REFUSAL: Final[str] = "the number is too large to be held"
_TRUE_WORDS: Final[frozenset[str]] = frozenset({"true", "yes", "on", "y", "t", "1"})
_FALSE_WORDS: Final[frozenset[str]] = frozenset({"false", "no", "off", "n", "f", "0"})


def convert_cell(*, value: TableCellValue, kind: CellKind) -> CellConversion:
    """Convert a non-empty cell to a field's kind, by the MTHDS standard's rules for reading a spreadsheet.

    A text cell, which every CSV cell is: an integer from an integer literal, a number from a decimal with a dot and an
    optional sign and exponent but no grouping separator, a boolean from true/false, yes/no, on/off, y/n, t/f or 1/0
    ignoring case, a date or a datetime from ISO 8601 only, and a text as it is. Surrounding spaces are ignored but by a
    text. A typed workbook cell: a text takes it as its text (`_as_text`); an integer a number with no fractional part;
    a number any number; a boolean a boolean; a date a date or a datetime at midnight; a datetime a datetime or a date.
    A boolean is never a number, nor a number a boolean, and a number that is not finite, such as an exponent too large
    for a float, is refused.
    """
    if kind.is_text:
        return CellConversion(value=_as_text(value=value))
    if isinstance(value, str):
        return _convert_text(text=value.strip(), kind=kind)
    match kind:
        case CellKind.INTEGER:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return CellConversion(value=None, refusal="the cell does not hold a number, where an integer is expected")
            if isinstance(value, float) and not math.isfinite(value):
                return CellConversion(value=None, refusal=_NOT_FINITE_REFUSAL)
            if isinstance(value, float) and not value.is_integer():
                return CellConversion(value=None, refusal="the cell holds a number with a fractional part, where an integer is expected")
            return CellConversion(value=int(value))
        case CellKind.NUMBER:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return CellConversion(value=None, refusal="the cell does not hold a number")
            if isinstance(value, float) and not math.isfinite(value):
                return CellConversion(value=None, refusal=_NOT_FINITE_REFUSAL)
            return CellConversion(value=value)
        case CellKind.BOOLEAN:
            if not isinstance(value, bool):
                return CellConversion(value=None, refusal="the cell does not hold a boolean")
            return CellConversion(value=value)
        case CellKind.DATE:
            if isinstance(value, datetime):
                if value.time() != time(0, 0) or value.tzinfo is not None:
                    return CellConversion(value=None, refusal="the cell holds a time of day, where a date is expected")
                return CellConversion(value=value.date())
            if isinstance(value, date):
                return CellConversion(value=value)
            return CellConversion(value=None, refusal="the cell does not hold a date")
        case CellKind.DATETIME:
            if isinstance(value, datetime):
                return CellConversion(value=value)
            if isinstance(value, date):
                return CellConversion(value=datetime.combine(value, time(0, 0)))
            return CellConversion(value=None, refusal="the cell does not hold a date or a datetime")
        case CellKind.TEXT:
            return CellConversion(value=_as_text(value=value))


def _convert_text(*, text: str, kind: CellKind) -> CellConversion:
    """Convert a text cell, spaces around it removed, to a field's kind that is not a text."""
    match kind:
        case CellKind.INTEGER:
            if _INTEGER_LITERAL.fullmatch(text) is None:
                return CellConversion(value=None, refusal="the text is not an integer literal")
            try:
                return CellConversion(value=int(text))
            # Python refuses to read an integer of more digits than `sys.get_int_max_str_digits()` allows.
            except ValueError:
                return CellConversion(value=None, refusal="the integer has too many digits")
        case CellKind.NUMBER:
            if _DECIMAL_LITERAL.fullmatch(text) is None:
                return CellConversion(value=None, refusal="the text is not a decimal number written with a dot and no grouping separator")
            number = float(text)
            if not math.isfinite(number):
                return CellConversion(value=None, refusal=_TOO_LARGE_REFUSAL)
            return CellConversion(value=number)
        case CellKind.BOOLEAN:
            lowered = text.lower()
            if lowered in _TRUE_WORDS:
                return CellConversion(value=True)
            if lowered in _FALSE_WORDS:
                return CellConversion(value=False)
            return CellConversion(value=None, refusal="the text is not a boolean (true/false, yes/no, on/off, y/n, t/f or 1/0)")
        case CellKind.DATE:
            try:
                return CellConversion(value=date.fromisoformat(text))
            except ValueError:
                pass
            try:
                parsed_datetime = datetime.fromisoformat(text)
            except ValueError:
                return CellConversion(value=None, refusal="the text is not an ISO 8601 date")
            if parsed_datetime.time() != time(0, 0) or parsed_datetime.tzinfo is not None:
                return CellConversion(value=None, refusal="the text holds a time of day, where a date is expected")
            return CellConversion(value=parsed_datetime.date())
        case CellKind.DATETIME:
            try:
                return CellConversion(value=datetime.fromisoformat(text))
            except ValueError:
                return CellConversion(value=None, refusal="the text is not an ISO 8601 date or datetime")
        case CellKind.TEXT:
            return CellConversion(value=text)


def admits_integer(*, annotation: Any) -> bool:
    """Whether a flat field's annotation is an integer or a number, optional or not, which a row position can fill."""
    origin = get_origin(annotation)
    if origin in {Union, _UnionType}:
        non_none_args = [arg for arg in get_args(annotation) if arg is not _NONE_TYPE]
        return len(non_none_args) == 1 and admits_integer(annotation=non_none_args[0])
    return annotation is int or annotation is float


def _as_text(*, value: TableCellValue) -> TableCellValue:
    """A typed cell's value as the text a text field reads: a number as written, a date in ISO form, a boolean lowercased."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    # The shortest decimal form that reads back as the same number, as Python writes a float.
    return str(value)
