"""Reading sheet ranges and named ranges from workbooks Microsoft Excel and LibreOffice Calc saved themselves.

Every other test builds its workbook in code with openpyxl, which stores no cached value for a formula and writes defined
names, filters and stored cells its own way. These fixtures were saved by the programs, as `tests/data/workbooks/README.md`
describes, so the finder and the reader are checked against what a user's file actually holds.
"""

import io
import zipfile
from typing import Any

import pytest
from openpyxl import load_workbook

from pipelex.cogt.doc_gen.sheet_range import SheetRange, SheetRegion, resolve_sheet_range
from pipelex.config import TABLE_READING_FALLBACK
from pipelex.tools.tabular.exceptions import TableSelectionError
from pipelex.tools.tabular.table_records import RawTable, TableBinding
from pipelex.tools.tabular.table_selector import TableSelector
from pipelex.tools.tabular.xlsx_codec import read_xlsx_raw_table
from tests.helpers.paths import data_path

SUBJECT = "the workbook given for input 'expenses'"
PROGRAMS = ["excel", "libreoffice"]
HEADER = ["Merchant", "Category", "Amount"]
ROWS: list[list[Any]] = [["Rail Co", "Travel", 84.5], ["Cafe Nord", "Meals", 12], ["Paper Shop", "Office", 23.75]]


def _workbook_bytes(*, program: str, name: str) -> bytes:
    return data_path(f"workbooks/{program}/{name}.xlsx").read_bytes()


def _read(*, raw_bytes: bytes, table_selector: TableSelector) -> RawTable:
    return read_xlsx_raw_table(
        raw_bytes=raw_bytes, table_selector=table_selector, binding=TableBinding.STEP, limits=TABLE_READING_FALLBACK, subject=SUBJECT
    )


def _region(*, raw_bytes: bytes, sheet_range: SheetRange) -> SheetRegion:
    workbook = load_workbook(io.BytesIO(raw_bytes))
    value_workbook = load_workbook(io.BytesIO(raw_bytes), data_only=True)
    return resolve_sheet_range(workbook=workbook, value_workbook=value_workbook, sheet_range=sheet_range, subject=SUBJECT)


@pytest.mark.parametrize("program", PROGRAMS)
class TestXlsxSavedByOffice:
    def test_a_header_in_a1_with_data_rows_and_no_table_is_found_and_read(self, program: str) -> None:
        raw_bytes = _workbook_bytes(program=program, name="header_in_a1")

        region = _region(raw_bytes=raw_bytes, sheet_range=SheetRange())
        raw_table = _read(raw_bytes=raw_bytes, table_selector=TableSelector(sheet_range=SheetRange()))

        assert (region.header_row, region.first_column, region.last_column, region.last_row, region.totals_row_count) == (1, 1, 3, 4, 0)
        assert raw_table.header == HEADER
        assert [row.cells for row in raw_table.rows] == ROWS

    def test_a_header_on_row_3_under_a_title_and_a_blank_row_is_read_from_its_header_row(self, program: str) -> None:
        raw_bytes = _workbook_bytes(program=program, name="title_above_header")
        sheet_range = SheetRange(sheet="Expenses", header_row=3)

        region = _region(raw_bytes=raw_bytes, sheet_range=sheet_range)
        raw_table = _read(raw_bytes=raw_bytes, table_selector=TableSelector(sheet_range=sheet_range))

        assert (region.header_row, region.first_column, region.last_column, region.last_row, region.totals_row_count) == (3, 1, 3, 6, 0)
        assert [row.cells for row in raw_table.rows] == ROWS
        assert raw_table.rows[0].label == "row 4 of the sheet 'Expenses'"

    @pytest.mark.parametrize("sheet", ["Expenses", "Subtotal"], ids=["sum", "subtotal"])
    def test_a_totals_line_under_the_data_is_found_and_left_out_with_its_cached_value_stored(self, program: str, sheet: str) -> None:
        raw_bytes = _workbook_bytes(program=program, name="totals_line")
        sheet_range = SheetRange(sheet=sheet)

        region = _region(raw_bytes=raw_bytes, sheet_range=sheet_range)
        raw_table = _read(raw_bytes=raw_bytes, table_selector=TableSelector(sheet_range=sheet_range))
        cached_total = load_workbook(io.BytesIO(raw_bytes), data_only=True)[sheet]["C5"].value

        assert (region.header_row, region.last_row, region.totals_row_count, region.prefilled_row_count) == (1, 4, 1, 0)
        assert [row.cells for row in raw_table.rows] == ROWS
        assert raw_table.uncached_formula_columns == frozenset()
        assert cached_total == 120.25

    def test_a_filter_on_the_header_row_agrees_with_the_range_and_its_hidden_name_is_never_a_named_range(self, program: str) -> None:
        raw_bytes = _workbook_bytes(program=program, name="filter_on_header")
        workbook = load_workbook(io.BytesIO(raw_bytes))

        region = _region(raw_bytes=raw_bytes, sheet_range=SheetRange())

        assert workbook["Expenses"].auto_filter.ref == "A1:C4"
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        assert 'name="_xlnm._FilterDatabase"' in workbook_xml
        assert (region.header_row, region.last_column, region.last_row) == (1, 3, 4)
        for hidden_name in ("_xlnm._FilterDatabase", "_FilterDatabase"):
            with pytest.raises(TableSelectionError):
                _read(raw_bytes=raw_bytes, table_selector=TableSelector(table=hidden_name))

    def test_a_workbook_scoped_and_a_sheet_scoped_named_range_are_read_by_name(self, program: str) -> None:
        raw_bytes = _workbook_bytes(program=program, name="named_ranges")

        expenses = _read(raw_bytes=raw_bytes, table_selector=TableSelector(table="Expenses"))
        trips = _read(raw_bytes=raw_bytes, table_selector=TableSelector(table="Trips"))

        assert expenses.header == HEADER
        assert [row.cells for row in expenses.rows] == ROWS
        assert trips.header == ["Trip", "Km"]
        assert [row.cells for row in trips.rows] == [["Lyon", 465], ["Lille", 225]]
