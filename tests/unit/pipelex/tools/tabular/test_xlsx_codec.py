import io
import time
import zipfile
from datetime import datetime

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.config import TABLE_READING_FALLBACK
from pipelex.tools.tabular.exceptions import CsvReadError, TableSelectionError, TableTooLargeError
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_selector import TableSelector
from pipelex.tools.tabular.xlsx_codec import read_xlsx_raw_table
from tests.helpers.xlsx_workbooks import (
    add_table,
    empty_workbook,
    formula_with_cached_text,
    formula_with_cached_value,
    single_table_workbook,
    with_part_rewritten,
    with_table_ref,
    workbook_bytes,
)

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

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert raw_table.header == ["Item", "Amount", "Approved", "Due"]
        assert [row.cells for row in raw_table.rows] == [["Paper", 12.5, True, datetime(2026, 3, 4)], ["Ink", 3, False, None]]
        assert [row.label for row in raw_table.rows] == ["row 2 of Table 'Rows'", "row 3 of Table 'Rows'"]
        assert raw_table.uncached_formula_columns == frozenset()

    @pytest.mark.parametrize("table_name", ["Income", "income", "INCOME"])
    def test_reads_the_table_named_ignoring_case(self, table_name: str) -> None:
        raw_table = read_xlsx_raw_table(
            raw_bytes=_two_table_workbook(), table_selector=TableSelector(table=table_name), limits=TABLE_READING_FALLBACK, subject=SUBJECT
        )

        assert raw_table.header == ["source"]
        assert [row.cells for row in raw_table.rows] == [["Sales"], ["Grants"]]
        # Rows are named by their sheet row, as Excel shows them.
        assert raw_table.rows[0].label == "row 4 of Table 'Income'"

    @pytest.mark.parametrize(
        ("raw_bytes_name", "table_name", "expected_message"),
        [
            pytest.param("two", None, r"several Tables \('Expenses', 'Income'\) and the step names none", id="several-tables-none-named"),
            pytest.param("two", "Budget", r"no Table or named range named 'Budget'; the Tables it holds: 'Expenses', 'Income'", id="missing-table"),
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
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(table=table_name), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

    def test_the_totals_row_is_not_read_and_empty_rows_are(self) -> None:
        raw_bytes = single_table_workbook(header=["item", "amount"], rows=[["Paper", 2], [None, None], ["Ink", 3]], totals_row=["Total", 5])

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert [row.cells for row in raw_table.rows] == [["Paper", 2], [None, None], ["Ink", 3]]

    def test_a_formula_reads_its_cached_value(self) -> None:
        raw_bytes = formula_with_cached_value(
            xlsx_bytes=single_table_workbook(header=["quantity", "total"], rows=[[2, "=A2*21"]]),
            cached_value="42",
        )

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert raw_table.rows[0].cells == [2, 42]
        assert raw_table.uncached_formula_columns == frozenset()

    def test_a_formula_without_cached_value_reads_empty_and_is_reported(self) -> None:
        raw_bytes = single_table_workbook(header=["quantity", "total"], rows=[[2, "=A2*21"], [None, None]])

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert raw_table.rows[0].cells == [2, None]
        assert raw_table.uncached_formula_columns == frozenset({1})

    def test_a_formula_whose_cached_value_is_an_empty_text_is_not_reported_uncached(self) -> None:
        """A formula calculated to an empty text reads empty, and was calculated, so no column is reported."""
        raw_bytes = formula_with_cached_text(
            xlsx_bytes=single_table_workbook(header=["quantity", "flag"], rows=[[2, '=IF(A2>0,"","x")']]),
            cached_text="",
        )

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert raw_table.rows[0].cells == [2, None]
        assert raw_table.uncached_formula_columns == frozenset()

    def test_bytes_that_are_not_a_workbook_are_refused(self) -> None:
        with pytest.raises(CsvReadError, match="Could not open the workbook given for input 'budget' as an Excel workbook"):
            read_xlsx_raw_table(raw_bytes=b"item,amount\nPaper,2\n", table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

    def test_a_table_declaring_the_whole_sheet_is_refused_without_reading_it(self) -> None:
        """A tiny workbook declaring a Table over the whole sheet is refused in moments, not read cell by cell."""
        raw_bytes = with_table_ref(xlsx_bytes=single_table_workbook(header=["item", "amount"], rows=[["Paper", 2]]), ref="A1:XFD1048576")

        started_at = time.monotonic()
        with pytest.raises(TableTooLargeError, match=r"spans 2097152 cells, more than the 2000000 a table is read with") as exc_info:
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert time.monotonic() - started_at < 2
        assert exc_info.value.error_code == CoreCode.INPUT_TOO_LARGE
        # A count of cells is no size in bytes, so the problem withholds both numbers.
        assert exc_info.value.problem_params() == {"input": None}

    def test_a_table_declaring_rows_past_its_sheet_reads_them_without_touching_the_sheet(self) -> None:
        """The declared rows past the sheet are empty data rows, made without creating a cell for each."""
        raw_bytes = with_table_ref(xlsx_bytes=single_table_workbook(header=["item", "amount"], rows=[["Paper", 2]]), ref="A1:J100000")

        started_at = time.monotonic()
        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert time.monotonic() - started_at < 2
        assert raw_table.header == ["item", "amount"]
        assert len(raw_table.rows) == 99_999
        assert raw_table.rows[0].cells == ["Paper", 2]
        assert raw_table.rows[-1].cells == [None, None]

    def test_a_table_declared_past_the_sheet_columns_counts_its_rows_and_is_refused(self) -> None:
        """A Table declared over a column holding no cell counts every declared row, one cell wide, and has no header."""
        raw_bytes = with_table_ref(xlsx_bytes=single_table_workbook(header=["item"], rows=[]), ref="ZZ1:ZZ1048576")
        limits = TableReadingConfig(max_workbook_uncompressed_bytes=10_000_000, max_table_cells=1000)

        started_at = time.monotonic()
        with pytest.raises(TableTooLargeError, match=r"spans 1048576 cells, more than the 1000 a table is read with"):
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=limits, subject=SUBJECT)
        # Under the cap, a Table with no column within the sheet is refused, since no header cell names a column.
        with pytest.raises(CsvReadError, match=r"Table 'Rows' of the workbook given for input 'budget' has no column within the sheet's cells"):
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert time.monotonic() - started_at < 2

    def test_rows_past_the_sheet_are_empty_data_rows_and_columns_past_it_are_dropped(self) -> None:
        raw_bytes = with_table_ref(xlsx_bytes=single_table_workbook(header=["item", "amount"], rows=[["Paper", 2]]), ref="A1:J4")

        raw_table = read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)

        assert raw_table.header == ["item", "amount"]
        assert [row.cells for row in raw_table.rows] == [["Paper", 2], [None, None], [None, None]]
        assert [row.label for row in raw_table.rows] == ["row 2 of Table 'Rows'", "row 3 of Table 'Rows'", "row 4 of Table 'Rows'"]

    def test_a_table_over_the_cell_cap_is_refused(self) -> None:
        raw_bytes = single_table_workbook(header=["item", "amount"], rows=[["Paper", 2], ["Ink", 3]])
        limits = TableReadingConfig(max_workbook_uncompressed_bytes=10_000_000, max_table_cells=5)

        with pytest.raises(TableTooLargeError, match=r"spans 6 cells, more than the 5 a table is read with"):
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=limits, subject=SUBJECT)

    def test_a_workbook_past_the_decompressed_size_is_refused_before_it_is_loaded(self) -> None:
        raw_bytes = single_table_workbook(header=["item"], rows=[["Paper"]])
        declared_size = sum(info.file_size for info in zipfile.ZipFile(io.BytesIO(raw_bytes)).infolist())
        limits = TableReadingConfig(max_workbook_uncompressed_bytes=declared_size - 1, max_table_cells=10)

        with pytest.raises(TableTooLargeError, match=r"once decompressed, more than the") as exc_info:
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=limits, subject=SUBJECT)

        assert exc_info.value.problem_params() == {"input": None, "limit": declared_size - 1, "size": declared_size}

    @pytest.mark.parametrize(
        "part_name",
        [
            pytest.param("xl/worksheets/sheet1.xml", id="truncated-worksheet"),
            pytest.param("xl/tables/table1.xml", id="truncated-table"),
            pytest.param("xl/workbook.xml", id="truncated-workbook-part"),
        ],
    )
    def test_a_workbook_with_a_truncated_xml_part_is_refused_as_unreadable(self, part_name: str) -> None:
        raw_bytes = with_part_rewritten(
            xlsx_bytes=single_table_workbook(header=["item"], rows=[["Paper"]]),
            part_name=part_name,
            rewrite=lambda content: content[: len(content) // 2],
        )

        with pytest.raises(CsvReadError, match="Could not open the workbook given for input 'budget' as an Excel workbook"):
            read_xlsx_raw_table(raw_bytes=raw_bytes, table_selector=TableSelector(), limits=TABLE_READING_FALLBACK, subject=SUBJECT)
