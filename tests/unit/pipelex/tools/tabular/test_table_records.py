"""Matching a table's header to a row concept and binding its rows, under a step's rules and a run input's.

The step's rules are the MTHDS standard's "Reading a Spreadsheet": unmatched columns are ignored, an ambiguous header,
two headers for one field and a header naming the row field are refused, and each cell converts by the standard's
rules, stricter than pydantic's lax mode.
"""

from datetime import date, datetime
from typing import Any, Literal

import pytest

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.tabular.exceptions import CsvCoercionError, CsvColumnError
from pipelex.tools.tabular.table_records import (
    CellKind,
    RawTable,
    RawTableRow,
    TableBinding,
    TableCellValue,
    TableFormat,
    TableRecords,
    admits_integer,
    build_table_records,
    cell_kind_of,
    convert_cell,
    list_content_from_table_records,
)

SUBJECT = "the workbook given for input 'budget'"


class BudgetLine(StructuredContent):
    line: int | None = None
    item: str
    amount: float | None = None
    quantity: int = 1
    approved: bool | None = None
    due: date | None = None
    status: Literal["open", "closed"] | None = None


FIELD_NAMES = list(BudgetLine.model_fields)


def _raw_table(*, header: list[str], rows: list[list[TableCellValue]], uncached: frozenset[int] | None = None) -> RawTable:
    return RawTable(
        header=header,
        rows=[RawTableRow(label=f"row {index_row + 2}", cells=cells) for index_row, cells in enumerate(rows)],
        uncached_formula_columns=uncached or frozenset(),
    )


def _step_records(*, header: list[str], rows: list[list[TableCellValue]], uncached: frozenset[int] | None = None) -> TableRecords:
    return build_table_records(
        raw_table=_raw_table(header=header, rows=rows, uncached=uncached),
        table_format=TableFormat.XLSX,
        field_names=FIELD_NAMES,
        row_field="line",
        binding=TableBinding.STEP,
        subject=SUBJECT,
    )


def _step_items(*, header: list[str], rows: list[list[TableCellValue]]) -> list[BudgetLine]:
    table_records = _step_records(header=header, rows=rows)
    content = list_content_from_table_records(
        table_records=table_records, row_model=BudgetLine, row_field="line", binding=TableBinding.STEP, subject=SUBJECT
    )
    return content.items


class TestTableRecords:
    def test_step_ignores_unmatched_columns_and_matches_headers_loosely(self) -> None:
        table_records = _step_records(header=["Item", "Comment", "AMOUNT", "Due date"], rows=[["Paper", "ignored", 12.5, None]])

        assert table_records.matched_fields == ["item", "amount"]
        assert table_records.records[0].values == {"item": "Paper", "amount": 12.5}
        assert table_records.records[0].position == 1

    def test_run_input_refuses_an_unmatched_column_by_its_position(self) -> None:
        with pytest.raises(CsvColumnError, match=r"Column\(s\) 2 of the workbook"):
            build_table_records(
                raw_table=_raw_table(header=["item", "comment"], rows=[["Paper", "x"]]),
                table_format=TableFormat.CSV,
                field_names=FIELD_NAMES,
                row_field=None,
                binding=TableBinding.RUN_INPUT,
                subject=SUBJECT,
            )

    def test_a_header_matching_several_fields_is_refused(self) -> None:
        with pytest.raises(CsvColumnError, match="matches several fields"):
            build_table_records(
                raw_table=_raw_table(header=["unit price"], rows=[]),
                table_format=TableFormat.XLSX,
                field_names=["unit_price", "unitprice"],
                row_field=None,
                binding=TableBinding.STEP,
                subject=SUBJECT,
            )

    def test_several_headers_matching_one_field_are_refused(self) -> None:
        with pytest.raises(CsvColumnError, match=r"columns 1, 3 of .* all match the field 'item'"):
            _step_records(header=["item", "amount", "Item"], rows=[])

    def test_a_header_matching_the_row_field_is_refused(self) -> None:
        with pytest.raises(CsvColumnError, match="receives each row's position") as exc_info:
            _step_records(header=["Line", "item"], rows=[])
        assert exc_info.value.given_params.get("field") == "line"

    def test_a_required_field_without_column_is_refused(self) -> None:
        table_records = _step_records(header=["amount"], rows=[[1.0]])
        with pytest.raises(CsvColumnError, match=r"Required field\(s\) \['item'\]"):
            list_content_from_table_records(
                table_records=table_records, row_model=BudgetLine, row_field="line", binding=TableBinding.STEP, subject=SUBJECT
            )

    def test_step_fills_positions_and_defaults(self) -> None:
        items = _step_items(header=["item", "quantity", "amount"], rows=[["Paper", None, ""], ["Pens", 3, 2], ["Ink", "4", "-1.5e2"]])

        assert [item.line for item in items] == [1, 2, 3]
        # An empty cell, or a column the table lacks, takes the field's default.
        assert items[0].quantity == 1
        assert items[0].amount is None
        assert items[0].approved is None
        assert items[2].quantity == 4
        assert items[2].amount == -150.0

    def test_an_empty_required_cell_is_refused_naming_the_row(self) -> None:
        with pytest.raises(CsvCoercionError, match=r"data row 2 \(row 3\)") as exc_info:
            _step_items(header=["item"], rows=[["Paper"], [None]])
        assert exc_info.value.given_params.get("field") == "item"

    def test_a_refused_conversion_names_the_row_position_and_the_field(self) -> None:
        with pytest.raises(CsvCoercionError) as exc_info:
            _step_items(header=["item", "amount"], rows=[["Paper", "1"], ["Ink", "1,5"]])
        message = str(exc_info.value)
        assert "data row 2 (row 3)" in message
        assert "field amount" in message
        assert "1,5" not in message
        assert exc_info.value.given_params.get("field") == "amount"

    def test_choices_are_checked_exactly(self) -> None:
        assert _step_items(header=["item", "status"], rows=[["Paper", "open"]])[0].status == "open"
        with pytest.raises(CsvCoercionError, match="field\\(s\\) status"):
            _step_items(header=["item", "status"], rows=[["Paper", "Open"]])

    def test_uncached_formula_columns_are_named_by_their_field(self) -> None:
        table_records = _step_records(header=["item", "notes", "amount"], rows=[["Paper", None, None]], uncached=frozenset({1, 2}))

        assert table_records.uncached_formula_fields == ["amount"]

    def test_records_round_trip_as_plain_data(self) -> None:
        table_records = _step_records(header=["item", "due"], rows=[["Paper", datetime(2026, 1, 2)]])

        assert TableRecords.model_validate_json(table_records.model_dump_json()) == table_records

    @pytest.mark.parametrize(
        ("value", "kind", "expected"),
        [
            pytest.param(42.0, CellKind.TEXT, "42", id="whole-number-to-text"),
            pytest.param(0.1, CellKind.TEXT, "0.1", id="decimal-to-text-shortest"),
            pytest.param(True, CellKind.TEXT, "true", id="boolean-to-text"),
            pytest.param(datetime(2026, 3, 4, 5, 6), CellKind.TEXT, "2026-03-04T05:06:00", id="datetime-to-text"),
            pytest.param(date(2026, 3, 4), CellKind.TEXT, "2026-03-04", id="date-to-text"),
            pytest.param(3.0, CellKind.INTEGER, 3, id="whole-float-to-integer"),
            pytest.param(7, CellKind.NUMBER, 7, id="integer-to-number"),
            pytest.param(False, CellKind.BOOLEAN, False, id="boolean"),
            pytest.param(datetime(2026, 3, 4), CellKind.DATE, date(2026, 3, 4), id="datetime-at-midnight-to-date"),
            pytest.param(date(2026, 3, 4), CellKind.DATETIME, datetime(2026, 3, 4), id="date-to-datetime"),
            pytest.param(" 12 ", CellKind.INTEGER, 12, id="text-integer-literal"),
            pytest.param("-3", CellKind.INTEGER, -3, id="text-negative-integer"),
            pytest.param("+2.5", CellKind.NUMBER, 2.5, id="text-signed-decimal"),
            pytest.param("1e3", CellKind.NUMBER, 1000.0, id="text-exponent"),
            pytest.param("YES", CellKind.BOOLEAN, True, id="text-yes"),
            pytest.param("off", CellKind.BOOLEAN, False, id="text-off"),
            pytest.param("T", CellKind.BOOLEAN, True, id="text-t"),
            pytest.param("0", CellKind.BOOLEAN, False, id="text-zero"),
            pytest.param("2026-03-04", CellKind.DATE, date(2026, 3, 4), id="text-iso-date"),
            pytest.param("2026-03-04T10:30:00", CellKind.DATETIME, datetime(2026, 3, 4, 10, 30), id="text-iso-datetime"),
            pytest.param("2026-03-04", CellKind.DATETIME, datetime(2026, 3, 4), id="text-iso-date-to-datetime"),
            pytest.param(" padded ", CellKind.TEXT, " padded ", id="text-kept-as-is"),
        ],
    )
    def test_convert_cell_accepts(self, value: TableCellValue, kind: CellKind, expected: Any) -> None:
        conversion = convert_cell(value=value, kind=kind)

        assert conversion.refusal is None
        assert conversion.value == expected
        assert type(conversion.value) is type(expected)

    @pytest.mark.parametrize(
        ("value", "kind"),
        [
            pytest.param(2.5, CellKind.INTEGER, id="fractional-number-to-integer"),
            pytest.param(True, CellKind.INTEGER, id="boolean-to-integer"),
            pytest.param(True, CellKind.NUMBER, id="boolean-to-number"),
            pytest.param(1, CellKind.BOOLEAN, id="number-to-boolean"),
            pytest.param(datetime(2026, 3, 4, 9, 0), CellKind.DATE, id="datetime-with-time-to-date"),
            pytest.param(12, CellKind.DATE, id="number-to-date"),
            pytest.param("1.0", CellKind.INTEGER, id="text-decimal-to-integer"),
            pytest.param("1,5", CellKind.NUMBER, id="text-decimal-comma"),
            pytest.param("1 234.5", CellKind.NUMBER, id="text-space-grouping"),
            pytest.param("1_000", CellKind.NUMBER, id="text-underscore-grouping"),
            pytest.param("1_000", CellKind.INTEGER, id="text-underscore-grouping-integer"),
            pytest.param("maybe", CellKind.BOOLEAN, id="text-unknown-boolean"),
            pytest.param("04/03/2026", CellKind.DATE, id="text-non-iso-date"),
            pytest.param("March 4, 2026", CellKind.DATETIME, id="text-non-iso-datetime"),
            pytest.param("2026-03-04T09:00", CellKind.DATE, id="text-datetime-with-time-to-date"),
        ],
    )
    def test_convert_cell_refuses(self, value: TableCellValue, kind: CellKind) -> None:
        conversion = convert_cell(value=value, kind=kind)

        assert conversion.refusal is not None
        assert str(value) not in conversion.refusal

    @pytest.mark.parametrize(
        ("annotation", "kind"),
        [
            pytest.param(str, CellKind.TEXT, id="text"),
            pytest.param(int | None, CellKind.INTEGER, id="optional-integer"),
            pytest.param(bool, CellKind.BOOLEAN, id="boolean-before-integer"),
            pytest.param(datetime, CellKind.DATETIME, id="datetime-before-date"),
            pytest.param(Literal["a", "b"], CellKind.TEXT, id="choices"),
            pytest.param(list[str], None, id="not-flat"),
        ],
    )
    def test_cell_kind_of(self, annotation: Any, kind: CellKind | None) -> None:
        assert cell_kind_of(annotation=annotation) == kind

    @pytest.mark.parametrize(
        ("annotation", "expected"),
        [
            pytest.param(int, True, id="integer"),
            pytest.param(float | None, True, id="optional-number"),
            pytest.param(str, False, id="text"),
            pytest.param(bool, False, id="boolean"),
        ],
    )
    def test_admits_integer(self, annotation: Any, expected: bool) -> None:
        assert admits_integer(annotation=annotation) is expected
