"""The table-read leaf reads a spreadsheet `Document` from storage into records, and refuses any other file by its input.

Storage is the in-memory provider; the workbooks are built in code.
"""

import threading
from pathlib import Path
from typing import Any, cast

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import table_read_generate
from pipelex.cogt.content_generation.assignment_models import TableReadAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.table_read_generate import read_table_of_document
from pipelex.cogt.doc_gen.sheet_range import SheetRange
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.tabular.exceptions import (
    CsvColumnError,
    TableFileTypeUnsupportedError,
    TableRangeUnclearError,
    TableReaderMisconfiguredError,
    TableTooLargeError,
)
from pipelex.tools.tabular.table_reading_config import TableReadingConfig
from pipelex.tools.tabular.table_records import TableFormat, TableRecords
from pipelex.tools.tabular.table_selector import TableSelector
from tests.helpers.xlsx_workbooks import sheet_workbook, single_table_workbook

_MODULE = "pipelex.cogt.content_generation.table_read_generate"
STORAGE_SCOPE = "org/method/run"
PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope=STORAGE_SCOPE, read_scope=None, user_id="u", pipeline_run_id="run"))


def _assignment(*, key: str, mime_type: str | None, file_name: str | None, table_selector: TableSelector | None = None) -> TableReadAssignment:
    return TableReadAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        source_uri=f"pipelex-storage://{key}",
        mime_type=mime_type,
        file_name=file_name,
        input_name="budget",
        field_names=["line", "item", "amount"],
        row_field="line",
        table_selector=table_selector or TableSelector(),
    )


async def _stored(*, mocker: MockerFixture, key: str, data: bytes) -> None:
    storage = InMemoryStorageProvider(root={})
    mocker.patch(f"{_MODULE}.get_storage_provider", return_value=storage)
    await storage.store(data=data, key=key)


class _ContentGeneratorPredatingTheRead:
    """A content generator that implements no `read_table`, as a host runtime's that predates it, and so inherits the default."""


@pytest.mark.asyncio(loop_scope="class")
class TestTableReadGenerate:
    async def test_a_workbook_in_storage_is_read_into_records(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.bin"
        await _stored(mocker=mocker, key=key, data=single_table_workbook(header=["Item", "Amount"], rows=[["Paper", 2.5], ["Ink", 3]]))

        table_records = await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type="application/octet-stream", file_name=None))

        assert table_records.table_format == TableFormat.XLSX
        assert [record.plain_values() for record in table_records.records] == [{"item": "Paper", "amount": 2.5}, {"item": "Ink", "amount": 3}]
        assert [record.position for record in table_records.records] == [1, 2]

    async def test_a_csv_file_in_storage_is_read_by_its_declared_type(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget"
        await _stored(mocker=mocker, key=key, data=b"Item,Amount,Comment\nPaper,2.5,x\n")

        table_records = await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type="text/csv", file_name=None))

        assert table_records.table_format == TableFormat.CSV
        assert table_records.records[0].plain_values() == {"item": "Paper", "amount": "2.5"}

    @pytest.mark.parametrize("mime_type", ["application/octet-stream", "application/vnd.ms-excel", "text/plain", "text/x-csv"])
    async def test_a_csv_file_declared_with_a_type_naming_no_table_format_is_read_by_its_name(self, mocker: MockerFixture, mime_type: str) -> None:
        key = f"{STORAGE_SCOPE}/assets/data.csv"
        await _stored(mocker=mocker, key=key, data=b"Item,Amount\nPaper,2.5\n")

        table_records = await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type=mime_type, file_name="data.csv"))

        assert table_records.table_format == TableFormat.CSV
        assert table_records.records[0].plain_values() == {"item": "Paper", "amount": "2.5"}

    async def test_the_file_is_read_off_the_event_loop_thread(self, mocker: MockerFixture) -> None:
        """Parsing a workbook is CPU-bound, so it runs on a worker thread and never blocks the event loop."""
        key = f"{STORAGE_SCOPE}/assets/budget.csv"
        await _stored(mocker=mocker, key=key, data=b"Item\nPaper\n")
        reading_threads: list[int] = []
        real_read = table_read_generate.read_table_records

        def _spy(**kwargs: Any) -> TableRecords:
            reading_threads.append(threading.get_ident())
            return real_read(**kwargs)

        mocker.patch(f"{_MODULE}.read_table_records", side_effect=_spy)

        await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type="text/csv", file_name=None))

        assert len(reading_threads) == 1
        assert reading_threads[0] != threading.get_ident()

    async def test_a_workbook_past_the_limits_is_refused_as_too_large_naming_the_input(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.xlsx"
        await _stored(mocker=mocker, key=key, data=single_table_workbook(header=["Item", "Amount"], rows=[["Paper", 2.5], ["Ink", 3]]))
        limits = TableReadingConfig(max_workbook_uncompressed_bytes=10_000_000, max_table_cells=4)
        mocker.patch(f"{_MODULE}.table_reading_limits", return_value=limits)

        with pytest.raises(TableTooLargeError) as exc_info:
            await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type=None, file_name="budget.xlsx"))

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_TOO_LARGE
        assert wire.get("params") == {"input": "budget"}, wire

    async def test_a_pdf_is_refused_as_an_unsupported_file_type_naming_the_input(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.pdf"
        await _stored(mocker=mocker, key=key, data=PDF_BYTES)

        with pytest.raises(TableFileTypeUnsupportedError) as exc_info:
            await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type=XLSX_MIME, file_name="budget.xlsx"))

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
        assert wire.get("params") == {"input": "budget", "format": "pdf", "model": "table_reader"}, wire
        assert "Input 'budget'" in str(exc_info.value)

    async def test_a_header_refusal_names_and_locates_the_input(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.xlsx"
        await _stored(mocker=mocker, key=key, data=single_table_workbook(header=["Item", "item"], rows=[]))

        with pytest.raises(CsvColumnError) as exc_info:
            await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type=None, file_name="budget.xlsx"))

        assert "the workbook given for input 'budget'" in str(exc_info.value)
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("params") == {"input": "budget", "field": "item"}, wire

    async def test_the_direct_content_generator_reads_the_range_the_step_s_selector_names(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.xlsx"
        cells = {"A1": "Budget 2026", "A3": "Item", "B3": "Amount", "A4": "Paper", "B4": 2.5, "A5": "Ink", "B5": 3, "B6": "=SUM(B4:B5)"}
        await _stored(mocker=mocker, key=key, data=sheet_workbook(cells=cells, sheet_title="Budget"))

        table_records = await ContentGenerator(generated_content_factory=mocker.MagicMock()).read_table(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            source_uri=f"pipelex-storage://{key}",
            mime_type=XLSX_MIME,
            file_name="budget.xlsx",
            input_name="budget",
            field_names=["line", "item", "amount"],
            row_field="line",
            table_selector=TableSelector(sheet_range=SheetRange(sheet="budget", header_row=3)),
        )

        assert [record.plain_values() for record in table_records.records] == [{"item": "Paper", "amount": 2.5}, {"item": "Ink", "amount": 3}]
        assert [record.position for record in table_records.records] == [1, 2]

    async def test_an_unclear_sheet_range_is_refused_as_the_input_s_naming_the_cell(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget.xlsx"
        await _stored(mocker=mocker, key=key, data=sheet_workbook(cells={"A1": "Item", "A2": "Paper", "A4": "note"}))
        assignment = _assignment(key=key, mime_type=XLSX_MIME, file_name="budget.xlsx", table_selector=TableSelector(sheet_range=SheetRange()))

        with pytest.raises(TableRangeUnclearError) as exc_info:
            await read_table_of_document(table_read_assignment=assignment)

        assert "Expenses!A4" in str(exc_info.value)
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_INVALID
        assert wire.get("params") == {"input": "budget", "field": "budget"}, wire

    async def test_a_content_generator_without_the_read_refuses_as_misconfigured(self) -> None:
        generator = cast("ContentGeneratorProtocol", _ContentGeneratorPredatingTheRead())

        with pytest.raises(TableReaderMisconfiguredError) as exc_info:
            await ContentGeneratorProtocol.read_table(
                generator,
                job_metadata=_job_metadata(),
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
                source_uri="pipelex-storage://org/method/run/assets/budget.xlsx",
                mime_type=XLSX_MIME,
                file_name="budget.xlsx",
                input_name="budget",
                field_names=["item"],
                row_field=None,
                table_selector=TableSelector(),
            )

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.RUNTIME_MISCONFIGURED
        assert "_ContentGeneratorPredatingTheRead" in str(exc_info.value)
