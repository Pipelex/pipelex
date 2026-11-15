import pytest

from pipelex.config import TABLE_READING_FALLBACK
from pipelex.tools.tabular.exceptions import CsvColumnError, TableSelectionError
from pipelex.tools.tabular.table_reader import read_table_records, table_format_key_of, table_format_of
from pipelex.tools.tabular.table_records import TableBinding, TableFormat, TableRecords
from tests.helpers.xlsx_workbooks import single_table_workbook

FIELD_NAMES = ["line", "item", "amount"]


def _read_csv(text: str, *, table_name: str | None = None) -> TableRecords:
    return read_table_records(
        raw_bytes=text.encode("utf-8"),
        table_format=TableFormat.CSV,
        field_names=FIELD_NAMES,
        row_field="line",
        table_name=table_name,
        binding=TableBinding.STEP,
        limits=TABLE_READING_FALLBACK,
        input_name="budget",
    )


class TestTableReader:
    @pytest.mark.parametrize(
        ("raw_bytes", "mime_type", "file_name", "expected"),
        [
            pytest.param(single_table_workbook(header=["item"], rows=[]), "application/octet-stream", "budget.bin", "xlsx", id="workbook-by-bytes"),
            pytest.param(single_table_workbook(header=["item"], rows=[]), None, None, "xlsx", id="workbook-by-bytes-alone"),
            pytest.param(b"item,amount\n", "text/csv", None, "csv", id="csv-by-media-type"),
            pytest.param(b"item,amount\n", None, "budget.CSV", "csv", id="csv-by-name"),
            pytest.param(b"%PDF-1.7\n", "text/csv", "budget.csv", "pdf", id="bytes-win-over-declarations"),
            pytest.param(b"item,amount\n", None, None, None, id="nothing-tells"),
            # A CSV file declared with a type that names no table format, as uploads commonly are, is known by its name.
            pytest.param(b"item,amount\n", "application/octet-stream", "data.csv", "csv", id="csv-declared-octet-stream"),
            pytest.param(b"item,amount\n", "application/csv", "data.csv", "csv", id="csv-declared-application-csv"),
            pytest.param(b"item,amount\n", "text/x-csv", "data.csv", "csv", id="csv-declared-text-x-csv"),
            pytest.param(b"item,amount\n", "text/plain", "data.csv", "csv", id="csv-declared-text-plain"),
            pytest.param(b"item,amount\n", "application/vnd.ms-excel", "data.csv", "csv", id="csv-declared-by-windows-excel"),
            # A declared type naming no table format stands when the name names none either.
            pytest.param(b"item,amount\n", "text/plain", "notes.txt", "txt", id="text-declared-and-named"),
        ],
    )
    def test_the_format_is_judged_from_bytes_then_media_type_then_name(
        self, raw_bytes: bytes, mime_type: str | None, file_name: str | None, expected: str | None
    ) -> None:
        format_key = table_format_key_of(raw_bytes=raw_bytes, mime_type=mime_type, file_name=file_name)

        assert format_key == expected

    @pytest.mark.parametrize(
        ("format_key", "expected"),
        [("csv", TableFormat.CSV), ("xlsx", TableFormat.XLSX), ("pdf", None), (None, None)],
    )
    def test_table_format_of(self, format_key: str | None, expected: TableFormat | None) -> None:
        assert table_format_of(format_key=format_key) == expected

    def test_a_table_named_for_a_csv_file_is_refused(self) -> None:
        with pytest.raises(TableSelectionError, match=r"reads the Table 'Budget'.*has no Tables"):
            _read_csv("item\nPaper\n", table_name="Budget")

    def test_csv_rows_counted_from_one_skipping_blank_lines(self) -> None:
        # A byte order mark is ignored; a blank physical line is skipped and not counted; a `,,` record is a data row; a
        # shorter record is padded with empty cells; a column matching no field is ignored on a step.
        table_records = _read_csv("﻿Item,Amount,Notes\nPaper,2,x\n\n,,\nInk\n")

        assert table_records.matched_fields == ["item", "amount"]
        assert [record.position for record in table_records.records] == [1, 2, 3]
        assert [record.label for record in table_records.records] == ["row 2", "row 4", "row 5"]
        assert [record.plain_values() for record in table_records.records] == [
            {"item": "Paper", "amount": "2"},
            {"item": None, "amount": None},
            {"item": "Ink", "amount": None},
        ]

    def test_a_csv_record_wider_than_the_header_is_refused(self) -> None:
        with pytest.raises(CsvColumnError):
            _read_csv("item,amount\nPaper,2,extra\n")

    def test_a_workbook_is_read_from_its_table(self) -> None:
        table_records = read_table_records(
            raw_bytes=single_table_workbook(header=["Item", "Amount"], rows=[["Paper", 2.5]], table_name="Budget"),
            table_format=TableFormat.XLSX,
            field_names=FIELD_NAMES,
            row_field="line",
            table_name="budget",
            binding=TableBinding.STEP,
            limits=TABLE_READING_FALLBACK,
            input_name="budget",
        )

        assert table_records.table_format == TableFormat.XLSX
        assert table_records.records[0].plain_values() == {"item": "Paper", "amount": 2.5}
