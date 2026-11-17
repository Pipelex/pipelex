"""A PipeDocGen step that fills a range on a sheet of the caller's workbook, a sheet holding no Excel Table.

The step's engine receives the sheet range, and so does its template checker. The method's load checks that the list
the range names is one of records of the step's data, carrying an update's matching fields, and refuses an engine that
does not declare the `sheet_range` capability. A range the shared finder cannot settle, which the checker lets
propagate, refuses the run as the caller's workbook's, naming the cell.
"""

import base64
import io
from collections.abc import Iterator
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from openpyxl import load_workbook
from openpyxl.worksheet.table import Table
from pytest_mock import MockerFixture

from pipelex.cogt.doc_gen.sheet_range import SheetRangeFill, resolve_sheet_range
from pipelex.cogt.doc_gen.table_fill import TableFill
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest, TemplateFinding
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenTemplateInputUnfitError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.tools.tabular.exceptions import TableRangeUnclearError
from tests.helpers.office_files import XLSX_MIME_TYPE
from tests.helpers.xlsx_workbooks import sheet_workbook, workbook_bytes
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, only_problem_item, refusal_messages

_CONCEPTS = """
domain = "doc_gen_sheet_range"
description = "Completing the caller's expense sheet"
main_pipe = "complete_expenses"

[concept.ExpenseLine]
description = "One expense line"

[concept.ExpenseLine.structure]
merchant = { type = "text", description = "The merchant", required = true }
row      = { type = "integer", description = "The line's position among the range's rows" }
category = { type = "text", description = "The expense's category" }

[concept.ExpenseNote]
description = "A note, which fills no range"

[concept.ExpenseNote.structure]
text = { type = "text", description = "The note's text", required = true }

[concept.ExpenseWorkbook]
description = "The caller's workbook with the lines added"
refines     = "Document"
"""

_EXPENSE_CELLS: dict[str, Any] = {"A1": "March expenses", "A3": "Merchant", "B3": "Category", "A4": "Rail Co", "B4": "travel"}


def _bundle(*, fill_fields: str = 'table_fill = "append"', sheet_range: str = '{ list = "lines", sheet = "Expenses", header_row = 3 }') -> str:
    return (
        _CONCEPTS
        + f"""
[pipe.complete_expenses]
type           = "PipeDocGen"
description    = "Add the lines to the caller's expense sheet"
inputs         = {{ workbook = "Document", lines = "ExpenseLine[]", notes = "ExpenseNote[]" }}
output         = "ExpenseWorkbook"
format         = "xlsx"
template_input = "workbook"
{fill_fields}
sheet_range    = {sheet_range}
"""
    )


def _inputs(*, workbook_bytes: bytes) -> dict[str, Any]:
    url = f"data:{XLSX_MIME_TYPE};base64,{base64.b64encode(workbook_bytes).decode('ascii')}"
    return {
        "workbook": {"concept": "native.Document", "content": {"url": url, "mime_type": XLSX_MIME_TYPE, "filename": "expenses.xlsx"}},
        "lines": {"concept": "doc_gen_sheet_range.ExpenseLine", "content": [{"merchant": "Cafe Nord", "row": 2, "category": "meals"}]},
        "notes": {"concept": "doc_gen_sheet_range.ExpenseNote", "content": [{"text": "Checked"}]},
    }


@pytest.fixture(autouse=True)
def restore_the_outer_library() -> Iterator[None]:
    """Tear down the library a validation left current, and restore the one the test started in."""
    outer_library_id = get_current_library_id_or_none()
    yield
    leaked_library_id = get_current_library_id_or_none()
    if leaked_library_id is not None and leaked_library_id != outer_library_id:
        get_library_manager().teardown(library_id=leaked_library_id)
    if outer_library_id is not None:
        set_current_library(library_id=outer_library_id)
    else:
        clear_current_library()


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenSheetRange:
    async def test_the_engine_and_its_checker_receive_the_sheet_range(self, sheet_range_xlsx_stub_engines: StubEngines) -> None:
        await PipelexMTHDSProtocol().execute(mthds_contents=[_bundle()], inputs=_inputs(workbook_bytes=sheet_workbook(cells=_EXPENSE_CELLS)))

        expected = SheetRangeFill(list="lines", sheet="Expenses", header_row=3)
        (job,) = sheet_range_xlsx_stub_engines.engine.jobs
        assert job.table_fill == TableFill.APPEND
        assert job.sheet_range == expected
        assert len(sheet_range_xlsx_stub_engines.check_requests) == 2
        assert all(request.sheet_range == expected for request in sheet_range_xlsx_stub_engines.check_requests)

    async def test_an_update_of_a_sheet_range_by_row_reaches_the_engine(self, sheet_range_xlsx_stub_engines: StubEngines) -> None:
        bundle = _bundle(fill_fields='table_fill = "update"\nmatch_row = "row"', sheet_range='{ list = "lines" }')

        await PipelexMTHDSProtocol().execute(mthds_contents=[bundle], inputs=_inputs(workbook_bytes=sheet_workbook(cells=_EXPENSE_CELLS)))

        (job,) = sheet_range_xlsx_stub_engines.engine.jobs
        assert (job.table_fill, job.match_row, job.sheet_range) == (TableFill.UPDATE, "row", SheetRangeFill(list="lines"))

    async def test_an_engine_that_does_not_fill_sheet_ranges_is_refused_when_the_method_loads(self, updating_xlsx_stub_engines: StubEngines) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_bundle()])

        item = only_problem_item(exc_info.value)
        assert item.code == CoreCode.MODEL_CAPABILITY_UNSUPPORTED
        assert item.params is not None
        assert item.params.model_dump(exclude_none=True) == {"model": "pipelex-xlsx", "capability": "sheet_range"}
        assert "to fill a range on a sheet holding no Excel Table (sheet_range)" in refusal_messages(exc_info.value)
        assert updating_xlsx_stub_engines.engine.jobs == []

    @pytest.mark.parametrize(
        ("fill_fields", "sheet_range", "expected_field", "expected_finding"),
        [
            (
                'table_fill = "append"',
                '{ list = "expenses" }',
                "sheet_range",
                "fills its range from the list 'expenses', which is no list of records of the step's data (its lists of records: 'lines', 'notes')",
            ),
            ('table_fill = "update"\nmatch_on = ["text"]', '{ list = "lines" }', "match_on", "the records of 'lines' have no field 'text'"),
            ('table_fill = "update"\nmatch_row = "row"', '{ list = "notes" }', "match_row", "the records of 'notes' have no field 'row'"),
        ],
        ids=["unknown-list", "key-the-list-lacks", "row-field-the-list-lacks"],
    )
    async def test_the_load_refuses_a_list_that_cannot_fill_the_range(
        self, sheet_range_xlsx_stub_engines: StubEngines, fill_fields: str, sheet_range: str, expected_field: str, expected_finding: str
    ) -> None:
        """Only the named list is held to the update's fields: the notes beside the lines do not refuse a key the lines carry."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_bundle(fill_fields=fill_fields, sheet_range=sheet_range)])

        item = only_problem_item(exc_info.value)
        assert item.params is not None
        params = item.params.model_dump(exclude_none=True)
        assert params["field_path"] == f"pipe.complete_expenses.{expected_field}"
        assert expected_finding in params["finding"]
        assert sheet_range_xlsx_stub_engines.engine.jobs == []

    async def test_an_update_matching_the_named_list_loads(self, sheet_range_xlsx_stub_engines: StubEngines) -> None:
        await validate_bundle(
            mthds_contents=[_bundle(fill_fields='table_fill = "update"\nmatch_on = ["merchant"]', sheet_range='{ list = "lines" }')]
        )

        assert sheet_range_xlsx_stub_engines.engine.jobs == []

    async def test_a_range_the_finder_cannot_settle_refuses_the_caller_s_workbook_naming_the_cell(
        self, sheet_range_xlsx_stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        refusal = TableRangeUnclearError(
            "The sheet 'Expenses' of the template holds a value in Expenses!A9, below the blank row 5 that ends the rows.",
            sheet="Expenses",
            cell="Expenses!A9",
        )
        mocker.patch.object(sheet_range_xlsx_stub_engines, "check_template", side_effect=refusal)

        with pytest.raises(PipeDocGenTemplateInputUnfitError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[_bundle()], inputs=_inputs(workbook_bytes=sheet_workbook(cells=_EXPENSE_CELLS)))

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.DOCGEN_TEMPLATE_INPUT_UNFIT
        assert "Expenses!A9" in exc_info.value.message
        assert "the input 'workbook'" in exc_info.value.message
        assert sheet_range_xlsx_stub_engines.engine.jobs == []

    async def test_a_table_without_a_header_row_the_finder_meets_refuses_the_caller_s_workbook_as_a_finding(
        self, sheet_range_xlsx_stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        """The finder's refusal of a Table with no header row is a range refusal, which the check reports, not an unreadable file."""
        workbook = load_workbook(io.BytesIO(sheet_workbook(cells={"A1": "Rail Co", "B1": "travel"})))
        workbook.active.add_table(Table(displayName="Lines", ref="A1:B1", headerRowCount=0))  # type: ignore[union-attr]

        def _check_with_the_finder(*, request: TemplateCheckRequest) -> list[TemplateFinding]:
            assert request.sheet_range is not None
            template_workbook = load_workbook(io.BytesIO(request.template), data_only=False)
            resolve_sheet_range(workbook=template_workbook, sheet_range=request.sheet_range, subject=request.template_name)
            return []

        mocker.patch.object(sheet_range_xlsx_stub_engines, "check_template", side_effect=_check_with_the_finder)

        with pytest.raises(PipeDocGenTemplateInputUnfitError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                mthds_contents=[_bundle(sheet_range='{ list = "lines" }')], inputs=_inputs(workbook_bytes=workbook_bytes(workbook))
            )

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.DOCGEN_TEMPLATE_INPUT_UNFIT
        assert "Table 'Lines'" in exc_info.value.message
        assert "Expenses!A1:B1, has no header row" in exc_info.value.message
        assert sheet_range_xlsx_stub_engines.engine.jobs == []
