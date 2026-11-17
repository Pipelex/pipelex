"""Reading a workbook's rows from a named range or a range on a sheet, as well as from an Excel Table."""

from typing import Any

import pytest
from openpyxl.worksheet.table import Table

from pipelex.cogt.doc_gen.sheet_range import SheetRange
from pipelex.config import TABLE_READING_FALLBACK
from pipelex.tools.tabular.exceptions import TableRangeUnclearError, TableSelectionError, TableTooLargeError
from pipelex.tools.tabular.table_reader import read_table_records
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_records import TableBinding, TableFormat, TableRecords
from pipelex.tools.tabular.table_selector import TableSelector
from pipelex.tools.tabular.xlsx_codec import read_xlsx_raw_table
from tests.helpers.xlsx_workbooks import add_table, empty_workbook, sheet_workbook, with_cached_values, with_defined_name, workbook_bytes

SUBJECT = "the workbook given for input 'expenses'"

EXPENSE_CELLS: dict[str, Any] = {
    "A1": "March expenses",
    "A3": "Merchant",
    "B3": "Amount",
    "A4": "Rail Co",
    "B4": 84.5,
    "A5": "Cafe Nord",
    "B5": 12,
    "A6": "Total",
    "B6": "=SUM(B4:B5)",
}


def _read(*, raw_bytes: bytes, table_selector: TableSelector, limits: TableReadingConfig = TABLE_READING_FALLBACK) -> TableRecords:
    return read_table_records(
        raw_bytes=raw_bytes,
        table_format=TableFormat.XLSX,
        field_names=["merchant", "amount", "line"],
        row_field="line",
        table_selector=table_selector,
        binding=TableBinding.STEP,
        limits=limits,
        input_name="expenses",
    )


class TestXlsxRegions:
    def test_a_sheet_range_is_read_without_the_title_above_and_the_totals_line_below(self) -> None:
        raw_table = read_xlsx_raw_table(
            binding=TableBinding.STEP,
            raw_bytes=sheet_workbook(cells=EXPENSE_CELLS),
            table_selector=TableSelector(sheet_range=SheetRange(header_row=3)),
            limits=TABLE_READING_FALLBACK,
            subject=SUBJECT,
        )

        assert raw_table.header == ["Merchant", "Amount"]
        assert [row.cells for row in raw_table.rows] == [["Rail Co", 84.5], ["Cafe Nord", 12]]
        assert [row.label for row in raw_table.rows] == ["row 4 of the sheet 'Expenses'", "row 5 of the sheet 'Expenses'"]

    @pytest.mark.parametrize("with_totals_line", [True, False], ids=["with-totals-line", "without"])
    def test_the_row_position_counts_the_data_rows_alone(self, with_totals_line: bool) -> None:
        cells = dict(EXPENSE_CELLS)
        if not with_totals_line:
            del cells["A6"], cells["B6"]

        table_records = _read(
            raw_bytes=sheet_workbook(cells=cells), table_selector=TableSelector(sheet_range=SheetRange(sheet="expenses", header_row=3))
        )

        assert [record.position for record in table_records.records] == [1, 2]

    def test_an_uncached_formula_of_a_sheet_range_is_reported(self) -> None:
        cells = {"A1": "merchant", "B1": "amount", "A2": "Rail Co", "B2": "=40+44.5"}

        raw_table = read_xlsx_raw_table(
            binding=TableBinding.STEP,
            raw_bytes=sheet_workbook(cells=cells),
            table_selector=TableSelector(sheet_range=SheetRange()),
            limits=TABLE_READING_FALLBACK,
            subject=SUBJECT,
        )

        assert raw_table.rows[0].cells == ["Rail Co", None]
        assert raw_table.uncached_formula_columns == frozenset({1})

    def test_an_unclear_sheet_range_is_refused_naming_the_cell(self) -> None:
        cells = {**EXPENSE_CELLS, "A9": "Approved by Ana"}

        with pytest.raises(TableRangeUnclearError) as exc_info:
            _read(raw_bytes=sheet_workbook(cells=cells), table_selector=TableSelector(sheet_range=SheetRange(header_row=3)))

        assert exc_info.value.cell == "Expenses!A9"
        assert SUBJECT in exc_info.value.message
        assert "Approved" not in exc_info.value.message

    def test_a_sheet_range_past_the_cell_cap_is_refused(self) -> None:
        limits = TableReadingConfig(max_workbook_uncompressed_bytes=10_000_000, max_table_cells=5)

        with pytest.raises(TableTooLargeError, match=r"The range on the sheet 'Expenses' of .* spans 6 cells, more than the 5"):
            _read(raw_bytes=sheet_workbook(cells=EXPENSE_CELLS), table_selector=TableSelector(sheet_range=SheetRange(header_row=3)), limits=limits)

    def test_a_sheet_range_on_a_sheet_holding_one_table_reads_the_table(self) -> None:
        workbook = empty_workbook()
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Lines", header=["Merchant", "Amount"], rows=[["Rail Co", 84.5]], top_row=2)

        table_records = _read(raw_bytes=workbook_bytes(workbook), table_selector=TableSelector(sheet_range=SheetRange()))

        assert table_records.records[0].label == "row 3 of Table 'Lines'"
        assert table_records.records[0].plain_values() == {"merchant": "Rail Co", "amount": 84.5}
        assert table_records.records[0].position == 1

    def test_a_table_is_read_before_a_named_range_and_a_named_range_when_no_table_has_the_name(self) -> None:
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=EXPENSE_CELLS), name="Lines", definition="Expenses!$A$3:$B$6")

        table_records = _read(raw_bytes=xlsx_bytes, table_selector=TableSelector(table="lines"))

        # The name declares its extent: the finder's totals line is a data row of a named range.
        assert [record.label for record in table_records.records] == [f"row {row} of the named range 'Lines'" for row in (4, 5, 6)]
        assert [record.position for record in table_records.records] == [1, 2, 3]

    def test_a_named_range_s_empty_header_cell_names_no_column(self) -> None:
        cells = {"A1": "merchant", "C1": "amount", "A2": "Rail Co", "B2": "ignored", "C2": 84.5}
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=cells), name="Lines", definition="Expenses!$A$1:$C$2")

        raw_table = read_xlsx_raw_table(
            binding=TableBinding.STEP,
            raw_bytes=xlsx_bytes,
            table_selector=TableSelector(table="Lines"),
            limits=TABLE_READING_FALLBACK,
            subject=SUBJECT,
        )

        assert raw_table.header == ["merchant", "amount"]
        assert raw_table.rows[0].cells == ["Rail Co", 84.5]

    def test_the_default_counts_tables_only(self) -> None:
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=EXPENSE_CELLS), name="Lines", definition="Expenses!$A$3:$B$5")

        with pytest.raises(TableSelectionError, match=r"holds no Excel Table: .* or read them from a range on a sheet with `sheet_range`"):
            _read(raw_bytes=xlsx_bytes, table_selector=TableSelector())

    def test_a_name_that_is_not_a_named_range_is_refused(self) -> None:
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=EXPENSE_CELLS), name="Rate", definition="Expenses!$B$4")

        with pytest.raises(TableRangeUnclearError, match="refers to the one cell Expenses!B4"):
            _read(raw_bytes=xlsx_bytes, table_selector=TableSelector(table="Rate"))

    def test_a_csv_file_is_refused_with_a_sheet_range(self) -> None:
        with pytest.raises(TableSelectionError, match="reads a range on a sheet"):
            read_table_records(
                raw_bytes=b"merchant,amount\nRail Co,84.5\n",
                table_format=TableFormat.CSV,
                field_names=["merchant", "amount"],
                row_field=None,
                table_selector=TableSelector(sheet_range=SheetRange()),
                binding=TableBinding.STEP,
                limits=TABLE_READING_FALLBACK,
                input_name="expenses",
            )

    def test_a_selector_names_a_table_or_a_sheet_range_not_both(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            TableSelector(table="Lines", sheet_range=SheetRange())


class TestXlsxRegionRefusalsByBinding:
    @pytest.mark.parametrize(
        ("binding", "expected_message"),
        [
            (TableBinding.STEP, "in the workbook, or read them from a range on a sheet with `sheet_range`."),
            (TableBinding.RUN_INPUT, "holds no Excel Table: define the rows to read as a Table (Insert > Table) in the workbook."),
        ],
        ids=["step", "run-input"],
    )
    def test_a_workbook_holding_no_table_is_refused_with_the_hint_its_reader_can_follow(self, binding: TableBinding, expected_message: str) -> None:
        with pytest.raises(TableSelectionError) as exc_info:
            read_xlsx_raw_table(
                raw_bytes=sheet_workbook(cells=EXPENSE_CELLS),
                table_selector=TableSelector(),
                binding=binding,
                limits=TABLE_READING_FALLBACK,
                subject=SUBJECT,
            )

        assert exc_info.value.message.endswith(expected_message)
        assert ("sheet_range" in exc_info.value.message) is binding.names_its_region

    @pytest.mark.parametrize(
        ("binding", "expected_message"),
        [
            (TableBinding.STEP, "and the step names none: name the Table to read with `table`."),
            (TableBinding.RUN_INPUT, "a workbook given as an input is read from its only Table: keep the rows to read in one Table of the workbook."),
        ],
        ids=["step", "run-input"],
    )
    def test_a_workbook_holding_several_tables_is_refused_with_the_hint_its_reader_can_follow(
        self, binding: TableBinding, expected_message: str
    ) -> None:
        workbook = empty_workbook()
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Expenses", header=["item"], rows=[["Paper"]])
        add_table(workbook=workbook, sheet_title="Sheet1", table_name="Income", header=["source"], rows=[["Sales"]], left_column=3)

        with pytest.raises(TableSelectionError) as exc_info:
            read_xlsx_raw_table(
                raw_bytes=workbook_bytes(workbook),
                table_selector=TableSelector(),
                binding=binding,
                limits=TABLE_READING_FALLBACK,
                subject=SUBJECT,
            )

        assert exc_info.value.message.endswith(expected_message)
        assert ("`table`" in exc_info.value.message) is binding.names_its_region


class TestXlsxRegionsOfTemplates:
    def test_rows_pre_filled_with_formulas_are_not_read(self) -> None:
        cells: dict[str, Any] = {"A1": "merchant", "B1": "amount", "C1": "with_tax", "A2": "Rail Co", "B2": 84.5}
        cells |= {f"C{row}": f'=IF(B{row}="","",B{row}*1.2)' for row in range(2, 501)}

        table_records = _read(raw_bytes=sheet_workbook(cells=cells), table_selector=TableSelector(sheet_range=SheetRange()))

        assert [record.label for record in table_records.records] == ["row 2 of the sheet 'Expenses'"]

    def test_a_named_range_past_the_sheet_s_grid_is_refused_before_any_cell_is_read(self) -> None:
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=EXPENSE_CELLS), name="Lines", definition="Expenses!$A$1048577:$A$1048578")

        with pytest.raises(TableRangeUnclearError, match="outside the sheet's grid"):
            _read(raw_bytes=xlsx_bytes, table_selector=TableSelector(table="Lines"))


def _raw_sheet_range(*, raw_bytes: bytes, sheet_range: SheetRange | None = None) -> list[list[Any]]:
    raw_table = read_xlsx_raw_table(
        binding=TableBinding.STEP,
        raw_bytes=raw_bytes,
        table_selector=TableSelector(sheet_range=sheet_range or SheetRange()),
        limits=TABLE_READING_FALLBACK,
        subject=SUBJECT,
    )
    return [row.cells for row in raw_table.rows]


# Paper with its amount merged down over the row under it, then Ink.
MERGED_AMOUNT_CELLS: dict[str, Any] = {"A1": "merchant", "B1": "amount", "A2": "Paper", "B2": 2, "A4": "Ink", "B4": 3}


class TestXlsxCellsOfARegion:
    def test_a_cell_merged_down_from_a_data_row_reads_as_the_merge_s_first_cell(self) -> None:
        rows = _raw_sheet_range(raw_bytes=sheet_workbook(cells=MERGED_AMOUNT_CELLS, merged=("B2:B3",)))

        assert rows == [["Paper", 2], [None, 2], ["Ink", 3]]

    def test_a_named_range_reads_a_merged_cell_as_the_merge_s_first_cell(self) -> None:
        xlsx_bytes = with_defined_name(
            xlsx_bytes=sheet_workbook(cells=MERGED_AMOUNT_CELLS, merged=("B2:B3",)), name="Lines", definition="Expenses!$A$1:$B$4"
        )

        raw_table = read_xlsx_raw_table(
            binding=TableBinding.STEP,
            raw_bytes=xlsx_bytes,
            table_selector=TableSelector(table="Lines"),
            limits=TABLE_READING_FALLBACK,
            subject=SUBJECT,
        )

        assert [row.cells for row in raw_table.rows] == [["Paper", 2], [None, 2], ["Ink", 3]]

    def test_a_merge_down_from_the_header_of_a_named_range_gives_its_rows_no_value(self) -> None:
        cells = {"A1": "merchant", "B1": "amount", "B2": 2}
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=cells, merged=("A1:A2",)), name="Lines", definition="Expenses!$A$1:$B$2")

        raw_table = read_xlsx_raw_table(
            binding=TableBinding.STEP,
            raw_bytes=xlsx_bytes,
            table_selector=TableSelector(table="Lines"),
            limits=TABLE_READING_FALLBACK,
            subject=SUBJECT,
        )

        assert [row.cells for row in raw_table.rows] == [[None, 2]]

    def test_a_computed_sheet_whose_formulas_store_their_values_is_read(self) -> None:
        cells = {"A1": "merchant", "B1": "amount", "A2": "=Source!A2", "B2": "=Source!B2", "A3": "=Source!A3", "B3": "=Source!B3"}
        xlsx_bytes = with_cached_values(xlsx_bytes=sheet_workbook(cells=cells), cached_values={"A2": "Paper", "B2": 2, "A3": "Ink", "B3": 3})

        assert _raw_sheet_range(raw_bytes=xlsx_bytes) == [["Paper", 2], ["Ink", 3]]

    def test_a_computed_sheet_storing_no_value_reads_no_row_and_counts_the_rows_not_read(self) -> None:
        cells = {"A1": "merchant", "B1": "amount", "A2": "=Source!A2", "B2": "=Source!B2", "A3": "=Source!A3", "B3": "=Source!B3"}

        table_records = _read(raw_bytes=sheet_workbook(cells=cells), table_selector=TableSelector(sheet_range=SheetRange()))

        assert table_records.records == []
        assert table_records.uncached_prefilled_row_count == 2

    def test_a_header_formula_storing_no_value_is_refused(self) -> None:
        cells = {"A1": "merchant", "B1": '=LOWER("AMOUNT")', "A2": "Paper", "B2": 2}

        with pytest.raises(TableRangeUnclearError, match="saved without its calculated values") as exc_info:
            _read(raw_bytes=sheet_workbook(cells=cells), table_selector=TableSelector(sheet_range=SheetRange()))

        assert exc_info.value.cell == "Expenses!B1"

    def test_a_labelled_total_under_pre_filled_rows_is_not_read(self) -> None:
        cells: dict[str, Any] = {"A1": "merchant", "B1": "amount", "A2": "Paper", "B2": 2, "A6": "Total", "B6": "=SUM(B2:B5)"}
        cells |= {f"B{row}": f'=IF(A{row}="","",1)' for row in range(3, 6)}
        xlsx_bytes = with_cached_values(xlsx_bytes=sheet_workbook(cells=cells), cached_values={"B3": "", "B4": "", "B5": "", "B6": 2})

        assert _raw_sheet_range(raw_bytes=xlsx_bytes) == [["Paper", 2]]

    def test_a_merge_carrying_a_value_into_the_columns_is_refused(self) -> None:
        cells = {"B1": "merchant", "C1": "amount", "A2": "Paper"}

        with pytest.raises(TableRangeUnclearError, match=r"merges the cells Expenses!A2:B2 across the edge"):
            _raw_sheet_range(raw_bytes=sheet_workbook(cells=cells, merged=("A2:B2",)))

    def test_a_filter_naming_no_range_of_cells_is_refused(self) -> None:
        with pytest.raises(TableRangeUnclearError, match="covers no range of cells"):
            _raw_sheet_range(raw_bytes=sheet_workbook(cells={"A1": "merchant", "B1": "amount", "A2": "Paper"}, filter_ref="A1:C"))


class TestXlsxRegionsOutsideTheGrid:
    def test_a_table_from_row_zero_is_refused(self) -> None:
        workbook = empty_workbook()
        worksheet = workbook.create_sheet(title="Expenses")
        worksheet["A1"], worksheet["B1"], worksheet["A2"], worksheet["B2"] = "merchant", "amount", "Paper", 2
        worksheet.add_table(Table(displayName="Lines", ref="A0:B3"))

        with pytest.raises(TableRangeUnclearError, match="covers cells outside the sheet's grid"):
            _read(raw_bytes=workbook_bytes(workbook), table_selector=TableSelector(table="Lines"))

    def test_a_named_range_from_row_zero_is_refused(self) -> None:
        xlsx_bytes = with_defined_name(xlsx_bytes=sheet_workbook(cells=EXPENSE_CELLS), name="Lines", definition="Expenses!$A$0:$B$3")

        with pytest.raises(TableRangeUnclearError, match="refers to cells outside the sheet's grid"):
            _read(raw_bytes=xlsx_bytes, table_selector=TableSelector(table="Lines"))
