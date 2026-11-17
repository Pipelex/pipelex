import io
import time
import zipfile
from pathlib import Path

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.config import TABLE_READING_FALLBACK
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.tabular.csv_codec import list_content_from_csv
from pipelex.tools.tabular.exceptions import CsvColumnError, TableSelectionError, TableTooLargeError
from pipelex.tools.tabular.table_reader import read_table_records, table_format_key_of, table_format_of
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_records import TableBinding, TableFormat, TableRecords
from pipelex.tools.tabular.table_selector import TableSelector
from tests.helpers.xlsx_workbooks import single_table_workbook, with_entries_reordered

FIELD_NAMES = ["line", "item", "amount"]

# A workbook whose `xl/` entries come after five others, so a sniffer reading only the first few names a bare zip.
LATE_WORKBOOK_ENTRIES = ["docProps/app.xml", "docProps/core.xml", "_rels/.rels", "[Content_Types].xml", "customXml/item1.xml"]


class _Line(StructuredContent):
    item: str
    amount: str | None = None


def _read_csv(text: str, *, table_name: str | None = None, limits: TableReadingConfig = TABLE_READING_FALLBACK) -> TableRecords:
    return read_table_records(
        raw_bytes=text.encode("utf-8"),
        table_format=TableFormat.CSV,
        field_names=FIELD_NAMES,
        row_field="line",
        table_selector=TableSelector(table=table_name),
        binding=TableBinding.STEP,
        limits=limits,
        input_name="budget",
    )


def _late_entry_workbook() -> bytes:
    return with_entries_reordered(xlsx_bytes=single_table_workbook(header=["item"], rows=[["Paper"]]), leading_names=LATE_WORKBOOK_ENTRIES)


def _plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index_entry in range(6):
            archive.writestr(f"notes/note{index_entry}.txt", "hello")
    return buffer.getvalue()


def _cell_limits(*, max_table_cells: int) -> TableReadingConfig:
    return TableReadingConfig(max_workbook_uncompressed_bytes=TABLE_READING_FALLBACK.max_workbook_uncompressed_bytes, max_table_cells=max_table_cells)


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
            # A workbook whose identifying entries come late sniffs as a bare zip: its parts tell it, when nothing else does.
            pytest.param(_late_entry_workbook(), "application/octet-stream", None, "xlsx", id="late-entry-workbook-nameless-octet-stream"),
            pytest.param(_late_entry_workbook(), None, None, "xlsx", id="late-entry-workbook-by-parts-alone"),
            pytest.param(_late_entry_workbook(), "application/zip", None, "xlsx", id="late-entry-workbook-declared-zip"),
            pytest.param(
                _late_entry_workbook(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                None,
                "docx",
                id="declared-docx-stands",
            ),
            pytest.param(_plain_zip(), "application/octet-stream", None, None, id="plain-zip-is-no-workbook"),
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

    @pytest.mark.parametrize(
        ("text", "max_table_cells", "is_refused"),
        [
            pytest.param("item,amount\nPaper,2\nInk,3\n", 6, False, id="at-the-cap"),
            pytest.param("item,amount\nPaper,2\nInk,3\n", 5, True, id="past-the-cap"),
            # A narrower line is padded to the header's width, so it counts as wide as the header.
            pytest.param("item,amount,notes\nPaper\n", 5, True, id="narrow-line-counts-the-header-width"),
            # A blank line holds no cell and is not counted.
            pytest.param("item,amount\n\n\n\nPaper,2\n", 4, False, id="blank-lines-not-counted"),
        ],
    )
    def test_a_csv_file_is_held_to_the_cell_cap(self, text: str, max_table_cells: int, is_refused: bool) -> None:
        limits = _cell_limits(max_table_cells=max_table_cells)
        if not is_refused:
            assert _read_csv(text, limits=limits).records
            return
        with pytest.raises(TableTooLargeError, match=rf"holds more than the {max_table_cells} cells a table is read with") as exc_info:
            _read_csv(text, limits=limits)

        assert exc_info.value.error_code == CoreCode.INPUT_TOO_LARGE

    def test_a_csv_file_of_a_million_cells_is_refused_while_it_is_parsed(self) -> None:
        """A 2 MB file of one-character cells stops parsing at the cap, before its records are built."""
        text = "item\n" + "a\n" * 1_000_000

        started_at = time.monotonic()
        with pytest.raises(TableTooLargeError, match=r"holds more than the 1000 cells"):
            _read_csv(text, limits=_cell_limits(max_table_cells=1000))

        assert time.monotonic() - started_at < 2

    def test_a_csv_run_input_is_held_to_the_cell_cap(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "lines.csv"
        csv_path.write_text("item,amount\nPaper,2\nInk,3\n", encoding="utf-8")

        with pytest.raises(TableTooLargeError, match=r"The CSV file given for input 'lines' holds more than the 5 cells"):
            list_content_from_csv(csv_path, row_model=_Line, input_name="lines", limits=_cell_limits(max_table_cells=5))

        assert len(list_content_from_csv(csv_path, row_model=_Line, input_name="lines", limits=_cell_limits(max_table_cells=6)).items) == 2

    def test_a_late_entry_workbook_without_type_or_name_is_read(self) -> None:
        raw_bytes = _late_entry_workbook()
        table_format = table_format_of(format_key=table_format_key_of(raw_bytes=raw_bytes, mime_type="application/octet-stream", file_name=None))
        assert table_format == TableFormat.XLSX

        table_records = read_table_records(
            raw_bytes=raw_bytes,
            table_format=table_format,
            field_names=FIELD_NAMES,
            row_field="line",
            table_selector=TableSelector(),
            binding=TableBinding.STEP,
            limits=TABLE_READING_FALLBACK,
            input_name="budget",
        )

        assert [record.plain_values() for record in table_records.records] == [{"item": "Paper"}]

    def test_a_csv_record_wider_than_the_header_is_refused(self) -> None:
        with pytest.raises(CsvColumnError):
            _read_csv("item,amount\nPaper,2,extra\n")

    def test_a_workbook_is_read_from_its_table(self) -> None:
        table_records = read_table_records(
            raw_bytes=single_table_workbook(header=["Item", "Amount"], rows=[["Paper", 2.5]], table_name="Budget"),
            table_format=TableFormat.XLSX,
            field_names=FIELD_NAMES,
            row_field="line",
            table_selector=TableSelector(table="budget"),
            binding=TableBinding.STEP,
            limits=TABLE_READING_FALLBACK,
            input_name="budget",
        )

        assert table_records.table_format == TableFormat.XLSX
        assert table_records.records[0].plain_values() == {"item": "Paper", "amount": 2.5}
