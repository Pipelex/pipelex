"""Run setup refuses a file a `PipeStructure` reading a spreadsheet is certain to fail on, before any step runs.

The step reads an Excel workbook or a CSV file with no model, so the reader, `table_reader`, stands where a model is
named, and no document converter helps: a converted PDF is no table either. The walk has its own tests; here the
consumer is given, and only the comparison with the file inputs is exercised.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineInputFormatUnsupportedError
from pipelex.pipeline.file_input_consumers import (
    TABLE_FORMAT_KEYS,
    FileConsumerKind,
    FileInputConsumer,
    check_file_inputs_against_consumers,
)
from pipelex.pipeline.input_normalizer import FileInputKind, IdentifiedFileInput
from pipelex.tools.tabular.table_records import TABLE_READER
from pipelex.tools.uri.resolved_uri import UriKind

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _check(*, mocker: MockerFixture, mime_type: str | None, can_convert_documents: bool = False, file_name: str | None = None) -> None:
    consumer = FileInputConsumer(
        slot_name="budget",
        consumed_path=("budget",),
        pipe_ref="budget_read.read_budget",
        pipe_code="read_budget",
        kind=FileConsumerKind.TABLE_READ,
        model=TABLE_READER,
        readable_formats=TABLE_FORMAT_KEYS,
        formats_read_by_every_model=TABLE_FORMAT_KEYS,
        reads_web_pages=False,
        is_conditional=False,
        asks_for_page_views=False,
    )
    mocker.patch("pipelex.pipeline.file_input_consumers.collect_file_input_consumers", return_value={"budget": [consumer]})
    file_input = IdentifiedFileInput(
        path=("budget",), kind=FileInputKind.DOCUMENT, uri_kind=UriKind.PIPELEX_STORAGE, mime_type=mime_type, file_name=file_name
    )
    conversions = check_file_inputs_against_consumers(
        entry_pipe=mocker.MagicMock(), file_inputs=[file_input], can_convert_documents=can_convert_documents
    )
    assert conversions == []


class TestFileInputTableReadCheck:
    @pytest.mark.parametrize("mime_type", [XLSX_MIME, "text/csv", None])
    def test_a_workbook_a_csv_file_or_an_unknown_format_passes(self, mocker: MockerFixture, mime_type: str | None) -> None:
        _check(mocker=mocker, mime_type=mime_type)

    @pytest.mark.parametrize("mime_type", ["application/vnd.ms-excel", "text/plain", "application/octet-stream", "text/x-csv"])
    def test_a_csv_file_declared_with_a_type_naming_no_table_format_passes_by_its_name(self, mocker: MockerFixture, mime_type: str) -> None:
        """The step judges such a file by its name and its bytes, so run setup leaves it to the step."""
        _check(mocker=mocker, mime_type=mime_type, file_name="data.csv")

    @pytest.mark.parametrize(
        ("mime_type", "format_key", "described"),
        [
            pytest.param("application/pdf", "pdf", "a PDF document (.pdf)", id="pdf"),
            pytest.param(DOCX_MIME, "docx", "a Word document (.docx)", id="word-even-with-a-converter"),
        ],
    )
    def test_another_format_is_refused_naming_the_reader(self, mocker: MockerFixture, mime_type: str, format_key: str, described: str) -> None:
        with pytest.raises(PipelineInputFormatUnsupportedError) as exc_info:
            _check(mocker=mocker, mime_type=mime_type, can_convert_documents=True)

        message = exc_info.value.message
        assert f"Input 'budget' is {described}: pipe 'read_budget' reads a table from it" in message
        assert message.endswith("Give an Excel workbook (.xlsx) or a CSV file (.csv) to a step reading a spreadsheet.")
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("params") == {"input": "budget", "format": format_key, "model": TABLE_READER}, wire
