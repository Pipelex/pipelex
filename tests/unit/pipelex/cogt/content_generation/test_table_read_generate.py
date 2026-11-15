"""The table-read leaf reads a spreadsheet `Document` from storage into records, and refuses any other file by its input.

Storage is the in-memory provider; the workbooks are built in code.
"""

from pathlib import Path
from typing import cast

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import TableReadAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.table_read_generate import read_table_of_document
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.tabular.exceptions import CsvColumnError, TableFileTypeUnsupportedError, TableReaderMisconfiguredError
from pipelex.tools.tabular.table_records import TableFormat
from tests.helpers.xlsx_workbooks import single_table_workbook

_MODULE = "pipelex.cogt.content_generation.table_read_generate"
STORAGE_SCOPE = "org/method/run"
PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(storage_scope=STORAGE_SCOPE, read_scope=None, user_id="u", pipeline_run_id="run"))


def _assignment(*, key: str, mime_type: str | None, file_name: str | None, table_name: str | None = None) -> TableReadAssignment:
    return TableReadAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        source_uri=f"pipelex-storage://{key}",
        mime_type=mime_type,
        file_name=file_name,
        input_name="budget",
        field_names=["line", "item", "amount"],
        row_field="line",
        table_name=table_name,
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
        assert [record.values for record in table_records.records] == [{"item": "Paper", "amount": 2.5}, {"item": "Ink", "amount": 3}]
        assert [record.position for record in table_records.records] == [1, 2]

    async def test_a_csv_file_in_storage_is_read_by_its_declared_type(self, mocker: MockerFixture) -> None:
        key = f"{STORAGE_SCOPE}/assets/budget"
        await _stored(mocker=mocker, key=key, data=b"Item,Amount,Comment\nPaper,2.5,x\n")

        table_records = await read_table_of_document(table_read_assignment=_assignment(key=key, mime_type="text/csv", file_name=None))

        assert table_records.table_format == TableFormat.CSV
        assert table_records.records[0].values == {"item": "Paper", "amount": "2.5"}

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
                table_name=None,
            )

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.RUNTIME_MISCONFIGURED
        assert "_ContentGeneratorPredatingTheRead" in str(exc_info.value)
