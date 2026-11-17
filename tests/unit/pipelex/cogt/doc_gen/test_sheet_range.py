"""The shared range finder: the sheet range's rules, a worksheet's one Table, and named ranges, on workbooks built in code."""

import time
from typing import Any

import pytest
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table

from pipelex.cogt.doc_gen.sheet_range import (
    RegionKind,
    SheetRange,
    SheetRegion,
    TotalsPlacement,
    cell_address,
    find_sheet_range,
    resolve_named_range,
    resolve_sheet_range,
    table_region,
)
from pipelex.tools.tabular.exceptions import TableRangeUnclearError, TableSelectionError
from tests.helpers.xlsx_workbooks import (
    add_table,
    empty_workbook,
    formula_workbook,
    sheet_workbook,
    value_workbook,
    with_cached_values,
    with_defined_name,
    workbook_bytes,
)

SUBJECT = "the workbook given for input 'expenses'"

# The standard's example: a title over a blank row, the header in row 3, two data rows, and a totals line.
EXAMPLE_CELLS: dict[str, Any] = {
    "A1": "March expenses",
    "A3": "Date",
    "B3": "Merchant",
    "C3": "Amount",
    "D3": "Category",
    "A4": "2026-03-02",
    "B4": "Rail Co",
    "C4": 84.5,
    "D4": "travel",
    "A5": "2026-03-03",
    "B5": "Cafe Nord",
    "C5": 12,
    "D5": "meals",
    "C6": "=SUM(C4:C5)",
}

# A header in A1 and three data rows.
PLAIN_CELLS: dict[str, Any] = {
    "A1": "item",
    "B1": "amount",
    "A2": "Paper",
    "B2": 2,
    "A3": "Ink",
    "B3": 3,
    "A4": "Pens",
    "B4": 4,
}


def _find_in(xlsx_bytes: bytes, *, header_row: int | None = None) -> SheetRegion:
    return find_sheet_range(
        worksheet=formula_workbook(xlsx_bytes).worksheets[0],
        value_worksheet=value_workbook(xlsx_bytes).worksheets[0],
        header_row=header_row,
        subject=SUBJECT,
    )


def _find(cells: dict[str, Any], *, header_row: int | None = None, cached_values: dict[str, Any] | None = None, **sheet_fields: Any) -> SheetRegion:
    xlsx_bytes = sheet_workbook(cells=cells, **sheet_fields)
    if cached_values:
        xlsx_bytes = with_cached_values(xlsx_bytes=xlsx_bytes, cached_values=cached_values)
    return _find_in(xlsx_bytes, header_row=header_row)


def _refusal(
    cells: dict[str, Any], *, header_row: int | None = None, cached_values: dict[str, Any] | None = None, **sheet_fields: Any
) -> TableRangeUnclearError:
    with pytest.raises(TableRangeUnclearError) as exc_info:
        _find(cells, header_row=header_row, cached_values=cached_values, **sheet_fields)
    return exc_info.value


def _resolve(xlsx_bytes: bytes, *, sheet_range: SheetRange) -> SheetRegion:
    return resolve_sheet_range(
        workbook=formula_workbook(xlsx_bytes), value_workbook=value_workbook(xlsx_bytes), sheet_range=sheet_range, subject=SUBJECT
    )


class TestFindSheetRange:
    def test_a_header_in_a1_and_its_rows(self) -> None:
        region = _find(PLAIN_CELLS)

        assert region == SheetRegion(
            kind=RegionKind.SHEET_RANGE,
            name=None,
            sheet_title="Expenses",
            header_row=1,
            first_column=1,
            last_column=2,
            last_row=4,
            totals_row_count=0,
            prefilled_row_count=0,
            uncached_prefilled_row_count=0,
            totals_placement=TotalsPlacement.AFTER_DATA_ROWS,
        )
        assert list(region.data_rows) == [2, 3, 4]
        assert region.nb_cells == 8
        assert region.label == "the range on the sheet 'Expenses'"

    def test_the_header_row_named_skips_the_title_above_and_the_totals_line_is_not_a_data_row(self) -> None:
        region = _find(EXAMPLE_CELLS, header_row=3)

        assert (region.header_row, region.first_column, region.last_column) == (3, 1, 4)
        assert list(region.data_rows) == [4, 5]
        assert list(region.totals_rows) == [6]

    def test_a_header_elsewhere_on_the_sheet_is_found_as_the_first_row_holding_a_value(self) -> None:
        cells = {"C5": "item", "D5": "amount", "C6": "Paper", "D6": 2}

        region = _find(cells)

        assert (region.header_row, region.first_column, region.last_column, region.last_row) == (5, 3, 4, 6)

    def test_a_title_above_the_header_without_header_row_is_refused_suggesting_it(self) -> None:
        refusal = _refusal(EXAMPLE_CELLS)

        assert refusal.cell == "Expenses!A3"
        assert "below the blank row 2" in refusal.message
        assert "name its row with `header_row`" in refusal.message

    @pytest.mark.parametrize(
        ("extra_cells", "expected_cell", "expected_finding"),
        [
            pytest.param({"A6": "Late"}, "Expenses!A6", "below the blank row 5", id="a-row-after-a-blank-row"),
            pytest.param({"B9": "Checked by Ana"}, "Expenses!B9", "below the blank row 5", id="a-note-below"),
            pytest.param({"C3": "aside"}, "Expenses!C3", "in the column just right of the columns", id="a-value-beside-a-data-row"),
            pytest.param({"D1": "second", "E1": "block"}, "Expenses!D1", "a second block of columns", id="a-second-header-block"),
        ],
    )
    def test_a_range_its_rules_cannot_settle_is_refused_naming_the_cell(
        self, extra_cells: dict[str, Any], expected_cell: str, expected_finding: str
    ) -> None:
        refusal = _refusal({**PLAIN_CELLS, **extra_cells})

        assert refusal.sheet == "Expenses"
        assert refusal.cell == expected_cell
        assert expected_finding in refusal.message
        assert expected_cell in refusal.message
        assert "turn the range into an Excel Table" in refusal.message

    def test_a_blank_row_inside_the_data_is_refused_naming_the_row_after_it(self) -> None:
        cells = {**PLAIN_CELLS, "A3": None, "B3": None}

        refusal = _refusal(cells)

        assert refusal.cell == "Expenses!A4"
        assert "below the blank row 3" in refusal.message

    def test_a_value_left_of_the_columns_is_a_column_with_no_header(self) -> None:
        cells = {"B1": "item", "C1": "amount", "B2": "Paper", "C2": 2, "A2": "aside"}

        refusal = _refusal(cells)

        assert refusal.cell == "Expenses!A2"
        assert "just left of the columns Expenses!B1:C1" in refusal.message

    def test_a_value_beside_the_totals_line_is_a_column_with_no_header(self) -> None:
        refusal = _refusal({**EXAMPLE_CELLS, "E6": "total"}, header_row=3)

        assert refusal.cell == "Expenses!E6"

    def test_values_past_the_empty_column_beside_the_range_are_left_alone(self) -> None:
        region = _find({**PLAIN_CELLS, "D2": "elsewhere", "D9": "note"})

        assert (region.last_column, region.last_row) == (2, 4)

    def test_values_above_the_header_row_named_are_not_part_of_the_range(self) -> None:
        region = _find({**PLAIN_CELLS, "A1": "Title", "B1": None, "C1": "aside", "A2": "item", "B2": "amount"}, header_row=2)

        assert (region.header_row, region.last_row) == (2, 4)

    @pytest.mark.parametrize(
        ("merged", "expected_cell"),
        [
            pytest.param("A1:B1", "Expenses!A1", id="two-headers-merged"),
            pytest.param("B1:C1", "Expenses!B1", id="the-last-header-merged-rightwards"),
            pytest.param("B1:B2", "Expenses!B1", id="a-header-merged-down"),
        ],
    )
    def test_a_header_cell_belonging_to_a_merged_range_is_refused_naming_it(self, merged: str, expected_cell: str) -> None:
        refusal = _refusal(PLAIN_CELLS, merged=(merged,))

        assert refusal.cell == expected_cell
        assert f"The header cell {expected_cell}" in refusal.message
        assert f"the merged cells Expenses!{merged}" in refusal.message

    def test_the_standard_s_merge_of_the_last_header_is_refused(self) -> None:
        """A horizontal merge on the last header, D3:E3, holds D3, a header cell of the range."""
        refusal = _refusal(EXAMPLE_CELLS, header_row=3, merged=("D3:E3",))

        assert refusal.cell == "Expenses!D3"

    def test_a_blank_merge_past_the_empty_column_on_the_header_row_is_read_fine(self) -> None:
        region = _find(PLAIN_CELLS, merged=("F1:G1",))

        assert (region.first_column, region.last_column, region.last_row) == (1, 2, 4)

    def test_a_merge_holding_a_value_further_along_the_header_row_is_a_second_block(self) -> None:
        refusal = _refusal({**PLAIN_CELLS, "F1": "Notes"}, merged=("F1:G1",))

        assert refusal.cell == "Expenses!F1"
        assert "a second block of columns" in refusal.message

    @pytest.mark.parametrize(
        "totals_formula",
        [
            pytest.param("=SUM(B2:B3)", id="sum"),
            pytest.param("=SUBTOTAL(109,$B$2:$B$3)", id="subtotal-absolute"),
            pytest.param("=SUM(Expenses!B2:B3)*1", id="same-sheet-qualified"),
        ],
    )
    def test_a_formula_totalling_its_column_above_is_a_totals_line(self, totals_formula: str) -> None:
        cells = {**PLAIN_CELLS, "A4": "Total", "B4": totals_formula}

        region = _find(cells)

        assert list(region.data_rows) == [2, 3]
        assert region.totals_row_count == 1

    @pytest.mark.parametrize(
        "last_row_formula",
        [
            pytest.param("=B2+B3", id="a-running-balance-written-without-a-colon"),
            pytest.param("=SUM(Other!B2:B3)", id="another-sheet"),
            pytest.param("=SUM(B:B)", id="a-whole-column"),
            pytest.param("=SUM(B2:B2)", id="not-through-the-row-above"),
            pytest.param("=SUM(A2:A3)", id="another-column"),
        ],
    )
    def test_any_other_formula_on_the_last_row_leaves_it_a_data_row(self, last_row_formula: str) -> None:
        region = _find({**PLAIN_CELLS, "B4": last_row_formula})

        assert list(region.data_rows) == [2, 3, 4]
        assert region.totals_row_count == 0

    def test_a_totals_line_typed_as_values_is_a_data_row(self) -> None:
        region = _find({**PLAIN_CELLS, "A4": "Total", "B4": 5})

        assert region.totals_row_count == 0

    def test_the_row_under_the_header_is_never_a_totals_line(self) -> None:
        region = _find({"A1": "item", "B1": "amount", "A2": "Total", "B2": "=SUM(B1:B1)"})

        assert list(region.data_rows) == [2]
        assert region.totals_row_count == 0

    def test_a_data_row_s_formula_with_no_cached_value_is_a_cell_of_its_row(self) -> None:
        """A workbook saved by openpyxl caches no formula's value: the row is a data row by its other cells."""
        region = _find({"A1": "item", "B1": "total", "A2": "Paper", "B2": "=1+1", "A3": "Ink", "B3": "=2+2"})

        assert (region.last_row, region.prefilled_row_count) == (3, 0)

    def test_rows_pre_filled_with_formulas_down_to_row_500_are_not_rows_of_the_range(self) -> None:
        cells: dict[str, Any] = {"A1": "item", "B1": "quantity", "C1": "price", "D1": "amount"}
        cells |= {"A2": "Paper", "B2": 2, "C2": 3.5, "A3": "Ink", "B3": 1, "C3": 12}
        cells |= {f"D{row}": f'=IF(A{row}="","",B{row}*C{row})' for row in range(2, 501)}

        region = _find(cells)

        assert list(region.data_rows) == [2, 3]
        assert region.totals_row_count == 0
        assert list(region.prefilled_rows) == list(range(4, 501))
        assert region.nb_cells == 12

    def test_a_totals_line_holding_only_its_formula_follows_the_data_rows_and_pre_filled_rows_follow_it(self) -> None:
        cells: dict[str, Any] = {"A1": "item", "B1": "amount", "C1": "double", "A2": "Paper", "B2": 2, "A3": "Ink", "B3": 3}
        cells |= {"C2": "=B2*2", "C3": "=B3*2", "B4": "=SUM(B2:B3)"}
        cells |= {f"C{row}": f'=IF(B{row}="","",B{row}*2)' for row in range(5, 9)}

        region = _find(cells)

        assert list(region.data_rows) == [2, 3]
        assert list(region.totals_rows) == [4]
        assert list(region.prefilled_rows) == [5, 6, 7, 8]

    @pytest.mark.parametrize("label", [None, "Total"], ids=["unlabelled", "labelled"])
    def test_a_total_under_the_pre_filled_rows_is_the_totals_line_after_them(self, label: str | None) -> None:
        """A row totalling its column from the first data row, after the pre-filled rows, is the range's totals line."""
        cells: dict[str, Any] = {"A1": "item", "B1": "amount", "A2": "Paper", "B2": 2, "A6": label}
        cells |= {f"B{row}": f'=IF(A{row}="","",1)' for row in range(3, 6)}
        cells["B6"] = "=SUM(B2:B5)"

        region = _find(cells, cached_values={"B3": "", "B4": "", "B5": "", "B6": 2})

        assert list(region.data_rows) == [2]
        assert list(region.prefilled_rows) == [3, 4, 5]
        assert list(region.totals_rows) == [6]
        assert region.totals_placement == TotalsPlacement.AFTER_PREFILLED_ROWS
        assert (region.last_sheet_row, region.uncached_prefilled_row_count, region.nb_cells) == (6, 0, 4)

    def test_a_value_beside_a_pre_filled_row_is_left_alone(self) -> None:
        """A pre-filled row is not a row of the range: a value beside it is no column with no header."""
        cells: dict[str, Any] = {"A1": "item", "B1": "amount", "A2": "Paper", "B2": 2, "B3": '=IF(A3="","",1)', "C3": "aside"}

        region = _find(cells)

        assert list(region.prefilled_rows) == [3]

    def test_data_below_pre_filled_rows_is_refused(self) -> None:
        cells: dict[str, Any] = {"A1": "item", "B1": "amount", "A2": "Paper", "B2": 2}
        cells |= {f"B{row}": f'=IF(A{row}="","",1)' for row in range(3, 10)}
        cells["A12"] = "Checked"

        refusal = _refusal(cells)

        assert refusal.cell == "Expenses!A12"
        assert "below row 3, which holds formulas and no data," in refusal.message

    def test_a_cell_merged_down_from_a_data_row_does_not_end_the_rows(self) -> None:
        cells = {"A1": "item", "B1": "amount", "A2": "Paper", "B2": 2, "A4": "Ink", "B4": 3}

        region = _find(cells, merged=("B2:B3",))

        assert list(region.data_rows) == [2, 3, 4]

    def test_a_merge_down_from_a_cell_holding_no_data_ends_the_rows(self) -> None:
        refusal = _refusal({"A1": "item", "B1": "amount", "A2": "Paper", "A4": "Ink"}, merged=("B2:B3",))

        assert refusal.cell == "Expenses!A4"

    @pytest.mark.parametrize(
        ("merged", "extra_cells", "expected_cell"),
        [
            pytest.param("A2:B2", {}, "Expenses!A2", id="the-only-row"),
            pytest.param("A3:B3", {"B2": "Ink", "C2": 3}, "Expenses!A3", id="the-row-after-the-data"),
            pytest.param("A2:B2", {"C2": 2}, "Expenses!A2", id="a-data-row"),
            pytest.param("C2:D2", {"B2": "Ink"}, "Expenses!C2", id="out-past-the-right-edge"),
        ],
    )
    def test_a_merge_crossing_the_columns_edge_is_refused_naming_it(self, merged: str, extra_cells: dict[str, Any], expected_cell: str) -> None:
        """Headers B1:C1, and a merge carrying a value into a header column from one with no header, or out of one."""
        anchor = merged.split(":", maxsplit=1)[0]
        cells = {"B1": "item", "C1": "amount", anchor: "Paper", **extra_cells}

        refusal = _refusal(cells, merged=(merged,))

        assert refusal.cell == expected_cell
        assert f"merges the cells Expenses!{merged} across the edge of the columns Expenses!B1:C1" in refusal.message
        assert "Paper" not in refusal.message

    def test_a_merge_wholly_inside_the_columns_keeps_the_merge_rules(self) -> None:
        cells = {"A1": "category", "B1": "item", "A2": "Office", "B2": "Paper", "B3": "Ink", "A4": "Travel", "B4": "Rail"}

        region = _find(cells, merged=("A2:A3",))

        assert list(region.data_rows) == [2, 3, 4]

    def test_a_computed_sheet_whose_formulas_store_their_values_reads_its_rows(self) -> None:
        """A sheet whose every row is formulas, as a view onto another sheet, holds data when the formulas store values."""
        cells = {"A1": "item", "B1": "amount", "A2": "=Source!A2", "B2": "=Source!B2", "A3": "=Source!A3", "B3": "=Source!B3"}

        region = _find(cells, cached_values={"A2": "Paper", "B2": 2, "A3": "Ink", "B3": 3})

        assert list(region.data_rows) == [2, 3]
        assert (region.prefilled_row_count, region.uncached_prefilled_row_count) == (0, 0)

    def test_a_running_balance_storing_its_value_is_a_data_row(self) -> None:
        cells = {"A1": "item", "B1": "amount", "C1": "balance", "A2": "Paper", "B2": 2, "C2": "=B2", "C3": "=C2+B3"}

        region = _find(cells, cached_values={"C2": 2, "C3": 2})

        assert list(region.data_rows) == [2, 3]

    def test_a_pre_fill_storing_empty_texts_is_still_pre_filled(self) -> None:
        cells: dict[str, Any] = {"A1": "item", "B1": "amount", "A2": "Paper", "B2": '=IF(A2="","",1)'}
        cells |= {f"B{row}": f'=IF(A{row}="","",1)' for row in range(3, 6)}

        region = _find(cells, cached_values={"B2": 1, "B3": "", "B4": "", "B5": ""})

        assert list(region.data_rows) == [2]
        assert list(region.prefilled_rows) == [3, 4, 5]
        assert region.uncached_prefilled_row_count == 0

    def test_formula_rows_storing_no_value_are_counted_as_uncached(self) -> None:
        """A workbook saved without its calculated values: rows of formulas may hold data, and are counted, not read."""
        cells = {"A1": "item", "B1": "amount", "A2": "=Source!A2", "B2": "=Source!B2", "A3": "=Source!A3", "B3": "=Source!B3"}

        region = _find(cells)

        assert list(region.data_rows) == []
        assert (region.prefilled_row_count, region.uncached_prefilled_row_count) == (2, 2)

    def test_a_header_formula_storing_no_value_is_refused_naming_its_cell(self) -> None:
        refusal = _refusal({"A1": "item", "B1": '=LOWER("AMOUNT")', "A2": "Paper", "B2": 2})

        assert refusal.cell == "Expenses!B1"
        assert "saved without its calculated values" in refusal.message
        assert "Open the workbook in Excel or LibreOffice and save it" in refusal.message

    def test_a_header_formula_storing_its_value_is_a_header(self) -> None:
        region = _find({"A1": "item", "B1": '=LOWER("AMOUNT")', "A2": "Paper", "B2": 2}, cached_values={"B1": "amount"})

        assert (region.last_column, region.last_row) == (2, 2)

    def test_a_filter_on_the_range_agrees(self) -> None:
        region = _find(PLAIN_CELLS, filter_ref="A1:B4")

        assert region.last_row == 4

    def test_a_filter_naming_no_range_of_cells_is_refused(self) -> None:
        """Openpyxl accepts a filter reference ending on a column with no row, which names no range of cells."""
        refusal = _refusal(PLAIN_CELLS, filter_ref="A1:C")

        assert refusal.sheet == "Expenses"
        assert "The filter of the sheet 'Expenses'" in refusal.message
        assert "covers no range of cells" in refusal.message

    @pytest.mark.parametrize("filter_ref", ["A2:B4", "A1:C4", "B1:B4"], ids=["below-the-header", "wider", "narrower"])
    def test_a_filter_that_disagrees_is_refused(self, filter_ref: str) -> None:
        refusal = _refusal(PLAIN_CELLS, filter_ref=filter_ref)

        assert f"covers {filter_ref}" in refusal.message

    def test_a_header_only_range_has_no_data_row(self) -> None:
        region = _find({"A1": "item", "B1": "amount"})

        assert list(region.data_rows) == []
        assert region.last_row == region.header_row == 1

    def test_an_empty_sheet_is_refused(self) -> None:
        refusal = _refusal({})

        assert "holds no value" in refusal.message
        assert refusal.cell is None

    def test_a_header_row_naming_an_empty_row_is_refused(self) -> None:
        refusal = _refusal(PLAIN_CELLS, header_row=7)

        assert "Row 7 of the sheet 'Expenses'" in refusal.message
        assert "holds no value" in refusal.message

    def test_formatted_empty_cells_below_the_data_hold_no_value(self) -> None:
        workbook = formula_workbook(sheet_workbook(cells=PLAIN_CELLS))
        worksheet = workbook.worksheets[0]
        for row in range(5, 40):
            worksheet.cell(row=row, column=1).font = Font(bold=True)
            worksheet.cell(row=row, column=2, value="")

        region = find_sheet_range(worksheet=worksheet, value_worksheet=worksheet, header_row=None, subject=SUBJECT)

        assert region.last_row == 4

    def test_a_sheet_whose_stored_cells_reach_the_last_row_costs_its_stored_cells(self) -> None:
        workbook = formula_workbook(sheet_workbook(cells=PLAIN_CELLS))
        worksheet = workbook.worksheets[0]
        worksheet.cell(row=1_048_576, column=2).font = Font(bold=True)
        assert worksheet.max_row == 1_048_576

        started = time.perf_counter()
        region = find_sheet_range(worksheet=worksheet, value_worksheet=worksheet, header_row=None, subject=SUBJECT)

        assert time.perf_counter() - started < 1
        assert region.last_row == 4

    def test_a_value_on_the_last_row_of_the_sheet_is_below_the_data(self) -> None:
        workbook = formula_workbook(sheet_workbook(cells=PLAIN_CELLS))
        worksheet = workbook.worksheets[0]
        worksheet.cell(row=1_048_576, column=1, value="note")

        with pytest.raises(TableRangeUnclearError) as exc_info:
            find_sheet_range(worksheet=worksheet, value_worksheet=worksheet, header_row=None, subject=SUBJECT)

        assert exc_info.value.cell == "Expenses!A1048576"

    def test_no_message_quotes_a_cell_s_value(self) -> None:
        refusal = _refusal({**PLAIN_CELLS, "B9": "Confidential salary note"})

        assert "Confidential" not in refusal.message

    def test_a_sheet_title_needing_quotes_is_quoted_in_addresses(self) -> None:
        assert cell_address(sheet_title="March 2026", row=12, column=3) == "'March 2026'!C12"
        assert cell_address(sheet_title="O'Neil", row=1, column=1) == "'O''Neil'!A1"
        assert cell_address(sheet_title="Expenses", row=1, column=1) == "Expenses!A1"


class TestResolveSheetRange:
    def test_the_only_worksheet_is_read_when_no_sheet_is_named(self) -> None:
        region = _resolve(sheet_workbook(cells=PLAIN_CELLS), sheet_range=SheetRange())

        assert region.sheet_title == "Expenses"

    def test_the_sheet_is_named_ignoring_case(self) -> None:
        region = _resolve(sheet_workbook(cells=PLAIN_CELLS, other_sheets=("Notes",)), sheet_range=SheetRange(sheet="EXPENSES"))

        assert region.sheet_title == "Expenses"

    @pytest.mark.parametrize(
        ("sheet", "expected_message"),
        [
            pytest.param(None, r"holds several worksheets \('Expenses', 'Notes'\) and the sheet range names none", id="several-none-named"),
            pytest.param("Budget", r"holds no worksheet named 'Budget'; its worksheets: 'Expenses', 'Notes'", id="missing"),
        ],
    )
    def test_a_worksheet_that_cannot_be_chosen_is_refused(self, sheet: str | None, expected_message: str) -> None:
        with pytest.raises(TableSelectionError, match=expected_message):
            _resolve(sheet_workbook(cells=PLAIN_CELLS, other_sheets=("Notes",)), sheet_range=SheetRange(sheet=sheet))

    def test_a_chart_sheet_is_not_a_worksheet(self) -> None:
        workbook = formula_workbook(sheet_workbook(cells=PLAIN_CELLS))
        workbook.create_chartsheet(title="Chart")

        region = resolve_sheet_range(workbook=workbook, value_workbook=workbook, sheet_range=SheetRange(), subject=SUBJECT)

        assert region.sheet_title == "Expenses"

    def test_a_worksheet_holding_one_table_reads_as_that_table(self) -> None:
        workbook = empty_workbook()
        add_table(
            workbook=workbook, sheet_title="Sheet1", table_name="Expenses", header=["item"], rows=[["Paper"], ["Ink"]], top_row=2, totals_row=["2"]
        )

        for header_row in (None, 2):
            region = _resolve(workbook_bytes(workbook), sheet_range=SheetRange(header_row=header_row))
            assert (region.kind, region.name, region.header_row, region.last_row, region.totals_row_count) == (RegionKind.TABLE, "Expenses", 2, 4, 1)

    def test_a_header_row_other_than_the_table_s_is_refused(self) -> None:
        workbook = empty_workbook()
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Expenses", header=["item"], rows=[["Paper"]], top_row=2)

        with pytest.raises(TableRangeUnclearError, match="whose header is row 2, and the sheet range's `header_row` names row 3") as exc_info:
            _resolve(workbook_bytes(workbook), sheet_range=SheetRange(header_row=3))
        assert exc_info.value.cell == "Sheet1!A2"

    def test_a_worksheet_holding_several_tables_is_refused_naming_them(self) -> None:
        workbook = empty_workbook()
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Expenses", header=["item"], rows=[["Paper"]])
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Income", header=["source"], rows=[["Sales"]], left_column=3)

        with pytest.raises(TableSelectionError, match=r"holds several Excel Tables \('Expenses', 'Income'\)"):
            _resolve(workbook_bytes(workbook), sheet_range=SheetRange())


def _named(definition: str, *, name: str = "Expenses", sheet_title: str | None = None) -> bytes:
    return with_defined_name(xlsx_bytes=sheet_workbook(cells=PLAIN_CELLS), name=name, definition=definition, sheet_title=sheet_title)


class TestResolveNamedRange:
    @pytest.mark.parametrize("sheet_title", [None, "Expenses"], ids=["workbook-scope", "sheet-scope"])
    def test_a_name_referring_to_one_range_is_a_named_range(self, sheet_title: str | None) -> None:
        workbook = formula_workbook(_named("Expenses!$A$1:$B$3", sheet_title=sheet_title))

        region = resolve_named_range(workbook=workbook, name="EXPENSES", subject=SUBJECT)

        assert region == SheetRegion(
            kind=RegionKind.NAMED_RANGE,
            name="Expenses",
            sheet_title="Expenses",
            header_row=1,
            first_column=1,
            last_column=2,
            last_row=3,
            totals_row_count=0,
            prefilled_row_count=0,
            uncached_prefilled_row_count=0,
            totals_placement=TotalsPlacement.AFTER_DATA_ROWS,
        )

    def test_a_name_the_workbook_does_not_define_is_none(self) -> None:
        assert resolve_named_range(workbook=formula_workbook(_named("Expenses!$A$1:$B$3")), name="Income", subject=SUBJECT) is None

    @pytest.mark.parametrize(
        "name",
        ["_xlnm._FilterDatabase", "__Anonymous_Sheet_DB__0"],
        ids=["excel-built-in", "libreoffice-database-range"],
    )
    def test_a_name_the_program_keeps_for_itself_is_never_a_named_range(self, name: str) -> None:
        workbook = formula_workbook(_named("Expenses!$A$1:$B$4", name=name, sheet_title="Expenses"))

        assert resolve_named_range(workbook=workbook, name=name, subject=SUBJECT) is None

    @pytest.mark.parametrize(
        ("definition", "expected_reason"),
        [
            pytest.param("OFFSET(Expenses!$A$1,0,0,3,2)", "holds a formula or a value", id="formula"),
            pytest.param("0.2", "holds a formula or a value", id="constant"),
            pytest.param("Expenses!$A$1:$A$2,Expenses!$B$1:$B$2", "refers to several ranges", id="several-areas"),
            pytest.param("Expenses!$A:$B", "refers to whole columns or rows", id="whole-columns"),
            pytest.param("Expenses!#REF!", "refers to cells that no longer exist", id="deleted-cells"),
            pytest.param("Gone!$A$1:$B$2", "refers to the sheet 'Gone'", id="missing-sheet"),
            pytest.param("Expenses!$B$2", "refers to the one cell Expenses!B2, too small to hold a header and rows", id="one-cell"),
            pytest.param(
                "Expenses!$A$1048577:$A$1048578", r"refers to cells outside the sheet's grid, from row 1 to row 1048576", id="past-the-last-row"
            ),
            pytest.param("Expenses!$XFD$1:$XFE$2", "from column A to column XFD", id="past-the-last-column"),
            pytest.param("Expenses!$A$0:$B$3", "refers to cells outside the sheet's grid", id="row-zero"),
        ],
    )
    def test_a_name_that_is_not_a_named_range_is_refused(self, definition: str, expected_reason: str) -> None:
        with pytest.raises(TableRangeUnclearError, match=expected_reason):
            resolve_named_range(workbook=formula_workbook(_named(definition)), name="Expenses", subject=SUBJECT)

    def test_a_name_defined_more_than_once_is_refused(self) -> None:
        xlsx_bytes = with_defined_name(
            xlsx_bytes=_named("Expenses!$A$1:$B$3"), name="Expenses", definition="Expenses!$A$1:$B$4", sheet_title="Expenses"
        )

        with pytest.raises(TableSelectionError, match="defines the name 'Expenses' more than once, for the workbook, the sheet 'Expenses'"):
            resolve_named_range(workbook=formula_workbook(xlsx_bytes), name="expenses", subject=SUBJECT)


class TestNamedRangeSheetTitles:
    @pytest.mark.parametrize("sheet_title", ["Données", "数据", "Q1.2026"], ids=["accented", "cjk", "dotted"])
    def test_a_title_excel_writes_bare_is_read(self, sheet_title: str) -> None:
        xlsx_bytes = with_defined_name(
            xlsx_bytes=sheet_workbook(cells=PLAIN_CELLS, sheet_title=sheet_title), name="Lines", definition=f"{sheet_title}!$A$1:$B$3"
        )

        region = resolve_named_range(workbook=formula_workbook(xlsx_bytes), name="Lines", subject=SUBJECT)

        assert region is not None
        assert (region.sheet_title, region.last_row) == (sheet_title, 3)


class TestTableRegion:
    def test_a_table_with_no_header_row_is_an_unclear_range_naming_its_cells(self) -> None:
        worksheet = formula_workbook(sheet_workbook(cells=PLAIN_CELLS)).worksheets[0]

        with pytest.raises(TableRangeUnclearError, match=r"Table 'Lines' of .*, over Expenses!A1:B4, has no header row") as exc_info:
            table_region(worksheet=worksheet, table=Table(displayName="Lines", ref="A1:B4", headerRowCount=0), subject=SUBJECT)

        assert (exc_info.value.sheet, exc_info.value.cell) == ("Expenses", "Expenses!A1")

    @pytest.mark.parametrize("ref", ["A1048575:B1048578", "XFC1:XFE3", "A0:B3"], ids=["past-the-last-row", "past-the-last-column", "row-zero"])
    def test_a_table_outside_the_sheet_s_grid_is_an_unclear_range(self, ref: str) -> None:
        worksheet = formula_workbook(sheet_workbook(cells=PLAIN_CELLS)).worksheets[0]

        with pytest.raises(TableRangeUnclearError, match="covers cells outside the sheet's grid"):
            table_region(worksheet=worksheet, table=Table(displayName="Lines", ref=ref), subject=SUBJECT)
