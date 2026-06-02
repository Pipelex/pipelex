"""Unit tests locking the CSV codec contract (Phase 1 — RED).

These exercise the codec in isolation (no library load, no pipe runtime): read/write row
primitives, the shared flatness classifier, concept-bound read/write with pydantic
coercion, the strict-column rules, the ``None`` <-> empty-cell mapping on both sides, the
empty-list header-only contract, the format seam, and the accept/reject coercion table.

All assertions are RED until Phase 2 fills in ``csv_codec`` — the skeleton currently
raises ``NotImplementedError`` from every function.
"""

import csv
from datetime import date
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import model_validator

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.tabular.csv_codec import (
    assert_supported_table_suffix,
    csv_from_list_content,
    flat_field_names,
    list_content_from_csv,
    read_rows,
    write_rows,
)
from pipelex.tools.tabular.exceptions import (
    CsvCoercionError,
    CsvColumnError,
    CsvError,
    CsvFlatnessError,
    CsvReadError,
)
from pipelex.types import Self, StrEnum

# ---------------------------------------------------------------------------------------
# Flat row models (CSV-legal: scalar fields only)
# ---------------------------------------------------------------------------------------


class FlatRow(StructuredContent):
    name: str
    age: int
    height: float
    active: bool
    born: date
    nickname: str | None = None


class IntRow(StructuredContent):
    value: int


class FloatRow(StructuredContent):
    value: float


class BoolRow(StructuredContent):
    value: bool


class DateRow(StructuredContent):
    value: date


class OptionalTextRow(StructuredContent):
    text: str | None = None


class RequiredTextRow(StructuredContent):
    text: str


class OptPairRow(StructuredContent):
    a: str | None = None
    b: str | None = None


class OrderedPairRow(StructuredContent):
    a: int
    b: int

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.a > self.b:
            msg = "a must be <= b"
            raise ValueError(msg)
        return self


class LiteralRow(StructuredContent):
    name: str
    rating: Literal["low", "high"]


class Grade(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class StrEnumRow(StructuredContent):
    name: str
    grade: Grade


class OptDefaultRow(StructuredContent):
    name: str
    nickname: str | None = "anon"


class IntDefaultRow(StructuredContent):
    name: str
    count: int = 0


class LabeledIntRow(StructuredContent):
    label: str
    number: int


# ---------------------------------------------------------------------------------------
# Non-flat row models (must be rejected by the flatness classifier)
# ---------------------------------------------------------------------------------------


class Priority(IntEnum):
    LOW = 1
    HIGH = 2


class IntLiteralRow(StructuredContent):
    value: Literal[1, 2, 3]


class IntEnumRow(StructuredContent):
    priority: Priority


class Inner(StructuredContent):
    x: int


class WithList(StructuredContent):
    tags: list[str]


class WithDict(StructuredContent):
    meta: dict[str, str]


class WithNested(StructuredContent):
    inner: Inner


class WithUnion(StructuredContent):
    value: int | str


class WithAny(StructuredContent):
    value: Any


def write_csv_file(directory: Path, content: str, name: str = "data.csv", encoding: str = "utf-8") -> Path:
    """Write *content* to ``directory/name`` and return the path."""
    path = directory / name
    path.write_text(content, encoding=encoding)
    return path


def write_value_csv(directory: Path, cell: str, name: str = "data.csv", header: str = "value") -> Path:
    """Write a one-column CSV with a single data cell, CSV-quoting it correctly.

    Building the data row through ``csv.writer`` (rather than an f-string) keeps a cell
    that contains the delimiter — e.g. the comma-decimal ``1,5`` — a single field instead
    of silently splitting it into two columns. An empty ``cell`` is written as a quoted
    ``""`` (a genuine empty-cell row that reads back as ``['']``), distinct from a blank
    physical line (``[]``) which the codec skips.
    """
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([header])
        writer.writerow([cell])
    return path


class TestCsvCodec:
    # ----------------------------------------------------------------------------------
    # read_rows / write_rows primitives
    # ----------------------------------------------------------------------------------

    def test_read_rows_happy(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "name,age\nAda,36\nGrace,85\n")
        rows = read_rows(path)
        assert rows == [{"name": "Ada", "age": "36"}, {"name": "Grace", "age": "85"}]

    def test_read_rows_custom_delimiter(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "name;age\nAda;36\n", name="semi.csv")
        rows = read_rows(path, delimiter=";")
        assert rows == [{"name": "Ada", "age": "36"}]

    def test_read_rows_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CsvReadError):
            read_rows(tmp_path / "does_not_exist.csv")

    def test_read_rows_bad_encoding_raises(self, tmp_path: Path) -> None:
        # 0xFF is not valid UTF-8; reading with utf-8 must surface a typed error.
        path = tmp_path / "latin.csv"
        path.write_bytes(b"name\nCaf\xe9\n")
        with pytest.raises(CsvReadError):
            read_rows(path, encoding="utf-8")

    def test_malformed_quote_raises(self, tmp_path: Path) -> None:
        # An unterminated quoted field: strict parsing must surface CsvReadError instead of silently
        # merging the following lines into one cell and running the pipeline on corrupted data.
        path = write_csv_file(tmp_path, 'name\n"unterminated\nAda\n')
        with pytest.raises(CsvReadError):
            read_rows(path)

    def test_duplicate_header_raises(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "name,name\nAda,Lovelace\n")
        with pytest.raises(CsvColumnError):
            read_rows(path)

    def test_blank_header_raises(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "name,,country\nAda,x,UK\n")
        with pytest.raises(CsvColumnError):
            read_rows(path)

    def test_write_rows_then_read_rows_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        rows = [{"name": "Ada", "age": "36"}, {"name": "Grace", "age": "85"}]
        write_rows(path, headers=["name", "age"], rows=rows)
        assert read_rows(path) == rows

    def test_write_rows_empty_writes_header_only(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.csv"
        write_rows(path, headers=["name", "age"], rows=[])
        text = path.read_text(encoding="utf-8")
        assert text.splitlines() == ["name,age"]

    # ----------------------------------------------------------------------------------
    # Flatness classifier (shared by read AND write)
    # ----------------------------------------------------------------------------------

    def test_flat_field_names_returns_declared_order(self) -> None:
        assert flat_field_names(FlatRow) == ["name", "age", "height", "active", "born", "nickname"]

    def test_flat_field_names_accepts_literal_scalar(self) -> None:
        assert flat_field_names(LiteralRow) == ["name", "rating"]

    def test_flat_field_names_accepts_str_enum(self) -> None:
        # A str-valued Enum (StrEnum) round-trips through a CSV cell, so it is flat.
        assert flat_field_names(StrEnumRow) == ["name", "grade"]

    @pytest.mark.parametrize(
        ("row_model", "offending_field"),
        [
            (WithList, "tags"),
            (WithDict, "meta"),
            (WithNested, "inner"),
            (WithUnion, "value"),
            (WithAny, "value"),
            # Non-string choices serialize but do not coerce back from a CSV string → not flat.
            (IntLiteralRow, "value"),
            (IntEnumRow, "priority"),
        ],
    )
    def test_flat_field_names_rejects_non_flat(self, row_model: type[StructuredContent], offending_field: str) -> None:
        with pytest.raises(CsvFlatnessError) as exc_info:
            flat_field_names(row_model)
        assert offending_field in str(exc_info.value)

    # ----------------------------------------------------------------------------------
    # list_content_from_csv — coercion + empty-cell semantics
    # ----------------------------------------------------------------------------------

    def test_list_content_from_csv_coerces_scalar_types(self, tmp_path: Path) -> None:
        path = write_csv_file(
            tmp_path,
            "name,age,height,active,born,nickname\nAda,36,1.7,true,1815-12-10,Countess\n",
        )
        list_content = list_content_from_csv(path, FlatRow)
        assert isinstance(list_content, ListContent)
        assert len(list_content.items) == 1
        item = list_content.items[0]
        assert item.name == "Ada"
        assert item.age == 36
        assert item.height == 1.7
        assert item.active is True
        assert item.born == date(1815, 12, 10)
        assert isinstance(item.born, date)
        assert item.nickname == "Countess"

    def test_empty_cell_on_optional_field_becomes_none(self, tmp_path: Path) -> None:
        path = write_csv_file(
            tmp_path,
            "name,age,height,active,born,nickname\nVint,82,1.8,true,1943-06-23,\n",
        )
        item = list_content_from_csv(path, FlatRow).items[0]
        assert item.nickname is None

    def test_empty_cell_on_required_field_raises(self, tmp_path: Path) -> None:
        # A genuine quoted-empty cell (not a blank line) -> None -> required int fails coercion.
        path = write_value_csv(tmp_path, "", name="req.csv")
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, IntRow)

    @pytest.mark.parametrize(
        ("row_model", "cell", "expected"),
        [
            (BoolRow, "true", True),
            (BoolRow, "false", False),
            (BoolRow, "1", True),
            (BoolRow, "0", False),
            (BoolRow, "yes", True),
            (BoolRow, "no", False),
            (BoolRow, "on", True),
            (BoolRow, "off", False),
            (IntRow, "42", 42),
            (FloatRow, "3.14", 3.14),
            (DateRow, "1815-12-10", date(1815, 12, 10)),
        ],
    )
    def test_coercion_accept_table(self, tmp_path: Path, row_model: type[StructuredContent], cell: str, expected: object) -> None:
        path = write_value_csv(tmp_path, cell)
        item = list_content_from_csv(path, row_model).items[0]
        assert item.model_dump()["value"] == expected

    @pytest.mark.parametrize(
        ("row_model", "cell"),
        [
            (IntRow, "abc"),
            (FloatRow, "1,5"),  # comma-decimal must be rejected, not silently parsed
            (DateRow, "31/12/2020"),  # ambiguous / non-ISO date must be rejected
        ],
    )
    def test_coercion_reject_table(self, tmp_path: Path, row_model: type[StructuredContent], cell: str) -> None:
        path = write_value_csv(tmp_path, cell)
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, row_model)

    def test_coercion_failure_names_row_and_field(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "value\n42\noops\n")
        with pytest.raises(CsvCoercionError) as exc_info:
            list_content_from_csv(path, IntRow)
        message = str(exc_info.value)
        assert "value" in message
        assert "row 3" in message  # 'oops' is on physical CSV line 3 (header=1, '42'=2, 'oops'=3)

    # ----------------------------------------------------------------------------------
    # Strict columns
    # ----------------------------------------------------------------------------------

    def test_extra_column_raises(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "value,surprise\n42,boom\n")
        with pytest.raises(CsvColumnError):
            list_content_from_csv(path, IntRow)

    def test_missing_required_column_raises(self, tmp_path: Path) -> None:
        # 'nickname' is optional so its absence is fine; drop a REQUIRED column ('name') instead.
        path = write_csv_file(tmp_path, "age,height,active,born,nickname\n36,1.7,true,1815-12-10,x\n", name="missing_req.csv")
        with pytest.raises(CsvColumnError):
            list_content_from_csv(path, FlatRow)

    def test_missing_optional_column_sets_field_none(self, tmp_path: Path) -> None:
        # 'nickname' (optional) column omitted entirely → None for every row (CT2 lenient).
        path = write_csv_file(tmp_path, "name,age,height,active,born\nAda,36,1.7,true,1815-12-10\n")
        item = list_content_from_csv(path, FlatRow).items[0]
        assert item.nickname is None
        assert item.name == "Ada"

    def test_missing_optional_column_is_none_not_model_default(self, tmp_path: Path) -> None:
        # CT2: an omitted NULLABLE column is None for every row even when the field has a NON-None
        # default ('anon') — the CSV is the source of truth, not the row model's construction default.
        path = write_csv_file(tmp_path, "name\nAda\n")
        item = list_content_from_csv(path, OptDefaultRow).items[0]
        assert item.nickname is None

    def test_missing_non_nullable_defaulted_column_keeps_default(self, tmp_path: Path) -> None:
        # A non-required but NON-nullable field (count: int = 0) keeps its own default when its column
        # is omitted — forcing None there would fail validation rather than honor the absence.
        path = write_csv_file(tmp_path, "name\nAda\n")
        item = list_content_from_csv(path, IntDefaultRow).items[0]
        assert item.count == 0

    # ----------------------------------------------------------------------------------
    # csv_from_list_content — write side
    # ----------------------------------------------------------------------------------

    def test_csv_from_list_content_writes_declared_header_and_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "people.csv"
        list_content: ListContent[FlatRow] = ListContent(
            items=[
                FlatRow(name="Ada", age=36, height=1.7, active=True, born=date(1815, 12, 10), nickname="Countess"),
                FlatRow(name="Grace", age=85, height=1.6, active=False, born=date(1906, 12, 9), nickname=None),
            ]
        )
        csv_from_list_content(list_content, row_model=FlatRow, path=path)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "name,age,height,active,born,nickname"
        # date serialized via model_dump(mode="json") → ISO string.
        assert lines[1].startswith("Ada,36,1.7,")
        assert "1815-12-10" in lines[1]
        # None must serialize to an empty cell, never the string "None".
        assert lines[2].endswith(",")
        assert "None" not in lines[2]

    def test_csv_from_empty_list_writes_header_only_from_model(self, tmp_path: Path) -> None:
        # CRITICAL: header comes from the declared model, never items[0].
        path = tmp_path / "empty.csv"
        empty: ListContent[FlatRow] = ListContent(items=[])
        csv_from_list_content(empty, row_model=FlatRow, path=path)
        assert path.read_text(encoding="utf-8").splitlines() == ["name,age,height,active,born,nickname"]

    def test_round_trip_stability(self, tmp_path: Path) -> None:
        path = tmp_path / "rt.csv"
        original: ListContent[FlatRow] = ListContent(
            items=[
                FlatRow(name="Ada", age=36, height=1.7, active=True, born=date(1815, 12, 10), nickname="Countess"),
                FlatRow(name="Grace", age=85, height=1.6, active=False, born=date(1906, 12, 9), nickname=None),
            ]
        )
        csv_from_list_content(original, row_model=FlatRow, path=path)
        reloaded = list_content_from_csv(path, FlatRow)
        assert reloaded.items == original.items

    # ----------------------------------------------------------------------------------
    # None <-> empty-cell, both sides
    # ----------------------------------------------------------------------------------

    def test_none_and_empty_string_both_write_blank_and_read_back_none(self, tmp_path: Path) -> None:
        path = tmp_path / "opt.csv"
        list_content: ListContent[OptionalTextRow] = ListContent(items=[OptionalTextRow(text=None), OptionalTextRow(text="")])
        csv_from_list_content(list_content, row_model=OptionalTextRow, path=path)
        reloaded = list_content_from_csv(path, OptionalTextRow)
        # Empty-string text is indistinguishable from None → both read back as None (documented).
        assert [item.text for item in reloaded.items] == [None, None]

    def test_required_text_empty_cell_rejected(self, tmp_path: Path) -> None:
        path = write_value_csv(tmp_path, "", name="reqtext.csv", header="text")
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, RequiredTextRow)

    # ----------------------------------------------------------------------------------
    # Phase-2 review findings (#2 blank lines, #3 over-wide rows, #4 delimiter/encoding,
    # #5 write item-type guard, #7 model-level coercion label)
    # ----------------------------------------------------------------------------------

    def test_blank_line_in_body_is_skipped(self, tmp_path: Path) -> None:
        # A blank physical line (csv yields []) is skipped, not turned into a phantom all-None row.
        path = write_csv_file(tmp_path, "a,b\nx,y\n\nz,w\n")
        items = list_content_from_csv(path, OptPairRow).items
        assert [(item.a, item.b) for item in items] == [("x", "y"), ("z", "w")]

    def test_row_wider_than_header_raises(self, tmp_path: Path) -> None:
        # A data row with more cells than the header has no column for the surplus → error, not silent drop.
        path = write_csv_file(tmp_path, "name,age\nAda,36,EXTRA\n")
        with pytest.raises(CsvColumnError):
            read_rows(path)

    # "\n"/"\r"/'"' are one character (so they pass the length check) but csv rejects them with a raw
    # ValueError; the codec must turn that into a typed CsvError, not let it escape the boundary.
    @pytest.mark.parametrize("bad_delimiter", ["", "||", "\n", "\r", '"'])
    def test_bad_delimiter_raises_on_read_and_write(self, tmp_path: Path, bad_delimiter: str) -> None:
        read_path = write_csv_file(tmp_path, "a,b\n1,2\n")
        with pytest.raises(CsvError):
            read_rows(read_path, delimiter=bad_delimiter)
        with pytest.raises(CsvError):
            write_rows(tmp_path / "out.csv", headers=["a"], rows=[], delimiter=bad_delimiter)

    def test_unknown_encoding_raises(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "a\n1\n")
        with pytest.raises(CsvReadError):
            read_rows(path, encoding="not-a-real-codec")

    def test_write_non_encodable_cell_raises(self, tmp_path: Path) -> None:
        # A cell that the target encoding can't represent must surface a typed CsvError on write,
        # not let a raw UnicodeEncodeError escape the codec boundary.
        with pytest.raises(CsvError):
            write_rows(tmp_path / "out.csv", headers=["name"], rows=[{"name": "café"}], encoding="ascii")

    def test_write_rejects_item_not_matching_row_model(self, tmp_path: Path) -> None:
        # An item whose class isn't the declared row_model would write silent empty cells → reject loudly.
        list_content: ListContent[StructuredContent] = ListContent(items=[IntRow(value=1)])
        with pytest.raises(CsvError):
            csv_from_list_content(list_content, row_model=RequiredTextRow, path=tmp_path / "x.csv")

    def test_coercion_error_names_model_level_failure(self, tmp_path: Path) -> None:
        # A model_validator failure has an empty pydantic loc; the message must still name the
        # row and concept (not the unhelpful "field(s) ?").
        path = write_csv_file(tmp_path, "a,b\n5,1\n")
        with pytest.raises(CsvCoercionError) as exc_info:
            list_content_from_csv(path, OrderedPairRow)
        message = str(exc_info.value)
        assert "field(s) ?" not in message
        # The offending row is the first data row, which is physical CSV line 2 (the header is line 1).
        assert "row 2" in message
        assert "OrderedPairRow" in message

    def test_coercion_error_row_number_after_multiline_cell(self, tmp_path: Path) -> None:
        # A valid quoted cell spanning two physical lines must not skew the line number of a later
        # bad row: the failing 'bad,oops' record starts on physical line 4 (header=1, multiline cell
        # =2-3), so the error must say "row 4", not "row 3".
        path = write_csv_file(tmp_path, 'label,number\n"multi\nline",1\nbad,oops\n')
        with pytest.raises(CsvCoercionError) as exc_info:
            list_content_from_csv(path, LabeledIntRow)
        assert "row 4" in str(exc_info.value)

    def test_coercion_error_row_number_counts_skipped_blank_lines(self, tmp_path: Path) -> None:
        # The reported row number is the physical CSV line, even when a blank line was skipped.
        path = write_csv_file(tmp_path, "value\n42\n\noops\n")
        with pytest.raises(CsvCoercionError) as exc_info:
            list_content_from_csv(path, IntRow)
        # 'oops' is on physical CSV line 4 (line 1 header, line 2 '42', line 3 blank, line 4 'oops').
        assert "row 4" in str(exc_info.value)

    # ----------------------------------------------------------------------------------
    # Format seam
    # ----------------------------------------------------------------------------------

    def test_supported_suffix_accepts_csv(self, tmp_path: Path) -> None:
        # No raise for .csv.
        assert_supported_table_suffix(tmp_path / "data.csv")

    def test_xlsx_suffix_points_at_tabular_extra(self, tmp_path: Path) -> None:
        with pytest.raises(CsvError) as exc_info:
            assert_supported_table_suffix(tmp_path / "data.xlsx")
        assert "pipelex[tabular]" in str(exc_info.value)

    def test_unsupported_suffix_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CsvError):
            assert_supported_table_suffix(tmp_path / "data.parquet")
