from datetime import datetime

import pytest

from pipelex.tools.tabular.exceptions import CsvReadError, TableSelectionError
from pipelex.tools.tabular.xlsx_codec import read_xlsx_raw_table
from tests.helpers.xlsx_workbooks import add_table, empty_workbook, formula_with_cached_value, single_table_workbook, workbook_bytes

SUBJECT = "the workbook given for input 'budget'"


def _two_table_workbook() -> bytes:
    workbook = empty_workbook()
    add_table(workbook=workbook, sheet_title="Sheet1", table_name="Expenses", header=["item"], rows=[["Paper"]])
    add_table(workbook=workbook, sheet_title="Other", table_name="Income", header=["source"], rows=[["Sales"], ["Grants"]], top_row=3, left_column=2)
    return workbook_bytes(workbook)


class TestXlsxCodec:
    def test_reads_the_only_table_with_typed_values(self) -> None:
        raw_bytes = single_table_workbook(
            header=["Item", "Amount", "Approved", "Due"],
            rows=[["Paper", 12.5, True, datetime(2026, 3, 4)], ["Ink", 3, False, None]],
        )

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=None, subject=SUBJECT)

        assert raw_table.header == ["Item", "Amount", "Approved", "Due"]
        assert [row.cells for row in raw_table.rows] == [["Paper", 12.5, True, datetime(2026, 3, 4)], ["Ink", 3, False, None]]
        assert [row.label for row in raw_table.rows] == ["row 2 of Table 'Rows'", "row 3 of Table 'Rows'"]
        assert raw_table.uncached_formula_columns == frozenset()

    @pytest.mark.parametrize("table_name", ["Income", "income", "INCOME"])
    def test_reads_the_table_named_ignoring_case(self, table_name: str) -> None:
        raw_table = read_xlsx_raw_table(raw_bytes=_two_table_workbook(), table_name=table_name, subject=SUBJECT)

        assert raw_table.header == ["source"]
        assert [row.cells for row in raw_table.rows] == [["Sales"], ["Grants"]]
        # Rows are named by their sheet row, as Excel shows them.
        assert raw_table.rows[0].label == "row 4 of Table 'Income'"

    @pytest.mark.parametrize(
        ("raw_bytes_name", "table_name", "expected_message"),
        [
            pytest.param("two", None, r"several Tables \('Expenses', 'Income'\) and the step names none", id="several-tables-none-named"),
            pytest.param("two", "Budget", r"no Table named 'Budget'; the Tables it holds: 'Expenses', 'Income'", id="missing-table"),
            pytest.param("none", None, "holds no Excel Table", id="no-table"),
            pytest.param("none", "Budget", "the Tables it holds: none", id="no-table-named"),
        ],
    )
    def test_a_table_that_cannot_be_chosen_is_refused_naming_the_tables_found(
        self, raw_bytes_name: str, table_name: str | None, expected_message: str
    ) -> None:
        if raw_bytes_name == "two":
            raw_bytes = _two_table_workbook()
        else:
            workbook = empty_workbook()
            workbook.create_sheet(title="Sheet1").append(["item"])
            raw_bytes = workbook_bytes(workbook)

        with pytest.raises(TableSelectionError, match=expected_message):
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=table_name, subject=SUBJECT)

    def test_the_totals_row_is_not_read_and_empty_rows_are(self) -> None:
        raw_bytes = single_table_workbook(header=["item", "amount"], rows=[["Paper", 2], [None, None], ["Ink", 3]], totals_row=["Total", 5])

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=None, subject=SUBJECT)

        assert [row.cells for row in raw_table.rows] == [["Paper", 2], [None, None], ["Ink", 3]]

    def test_a_formula_reads_its_cached_value(self) -> None:
        raw_bytes = formula_with_cached_value(
            xlsx_bytes=single_table_workbook(header=["quantity", "total"], rows=[[2, "=A2*21"]]),
            cached_value="42",
        )

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=None, subject=SUBJECT)

        assert raw_table.rows[0].cells == [2, 42]
        assert raw_table.uncached_formula_columns == frozenset()

    def test_a_formula_without_cached_value_reads_empty_and_is_reported(self) -> None:
        raw_bytes = single_table_workbook(header=["quantity", "total"], rows=[[2, "=A2*21"], [None, None]])

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_name=None, subject=SUBJECT)

        assert raw_table.rows[0].cells == [2, None]
        assert raw_table.uncached_formula_columns == frozenset({1})

    def test_bytes_that_are_not_a_workbook_are_refused(self) -> None:
        with pytest.raises(CsvReadError, match="Could not open the workbook given for input 'budget' as an Excel workbook"):
            read_xlsx_raw_table(raw_bytes=b"item,amount\nPaper,2\n", table_name=None, subject=SUBJECT)
