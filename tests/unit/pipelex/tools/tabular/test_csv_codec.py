"""Unit tests locking the CSV codec contract (Phase 1 — RED).

These exercise the codec in isolation (no library load, no pipe runtime): read/write row
primitives, the shared flatness classifier, concept-bound read/write with pydantic
coercion, the strict-column rules, the ``None`` <-> empty-cell mapping on both sides, the
empty-list header-only contract, the format seam, and the accept/reject coercion table.

All assertions are RED until Phase 2 fills in ``csv_codec`` — the skeleton currently
raises ``NotImplementedError`` from every function.
"""

from datetime import date
from pathlib import Path
from typing import Any, Literal

import pytest

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


class LiteralRow(StructuredContent):
    name: str
    rating: Literal["low", "high"]


# ---------------------------------------------------------------------------------------
# Non-flat row models (must be rejected by the flatness classifier)
# ---------------------------------------------------------------------------------------


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

    @pytest.mark.parametrize(
        ("row_model", "offending_field"),
        [
            (WithList, "tags"),
            (WithDict, "meta"),
            (WithNested, "inner"),
            (WithUnion, "value"),
            (WithAny, "value"),
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
        path = write_csv_file(tmp_path, "value\n\n", name="req.csv")
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, RequiredTextRow)

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
        path = write_csv_file(tmp_path, f"value\n{cell}\n")
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
        path = write_csv_file(tmp_path, f"value\n{cell}\n")
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, row_model)

    def test_coercion_failure_names_row_and_field(self, tmp_path: Path) -> None:
        path = write_csv_file(tmp_path, "value\n42\noops\n")
        with pytest.raises(CsvCoercionError) as exc_info:
            list_content_from_csv(path, IntRow)
        message = str(exc_info.value)
        assert "value" in message
        assert "2" in message  # the offending data row is the 2nd one (1-based)

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
        path = write_csv_file(tmp_path, "text\n\n", name="reqtext.csv")
        with pytest.raises(CsvCoercionError):
            list_content_from_csv(path, RequiredTextRow)

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
