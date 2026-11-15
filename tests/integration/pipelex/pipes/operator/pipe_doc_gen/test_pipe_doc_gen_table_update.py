"""A PipeDocGen step that updates the rows of the workbook its run supplies, matching each record to its row.

The step's engine receives the fill, the fields a record is matched to its row by and the cell policy, and so does its
template checker. Some list of records the step's data holds must carry those fields, which the method's load checks
once its concepts are known, and an engine that does not declare updating is refused when the method loads. The dry run
hands the checker no mock data under an update, since mock records match no real row.
"""

import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.doc_gen.table_fill import CellPolicy, TableFill
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.helpers.office_files import XLSX_MIME_TYPE, xlsx_bytes
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import METHOD_MANIFEST, StubEngines, only_problem_item, refusal_messages

_CONCEPTS = """
domain = "doc_gen_update"
description = "Completing the caller's expense workbook"
main_pipe = "complete_expenses"

[concept.ExpenseCompletion]
description = "The category found for one expense"

[concept.ExpenseCompletion.structure]
invoice_number = { type = "text", description = "The expense's invoice number, the Table's key", required = true }
row            = { type = "integer", description = "The expense's row in the Table" }
category       = { type = "text", description = "The expense's category, null when none was found" }

[concept.ExpenseReport]
description = "A report holding completions"

[concept.ExpenseReport.structure]
title       = { type = "text", description = "The report's title", required = true }
completions = { type = "list", item_type = "concept", item_concept_ref = "doc_gen_update.ExpenseCompletion", description = "Its completions" }

[concept.ExpenseNote]
description = "A note on the report, which fills no Table"

[concept.ExpenseNote.structure]
text = { type = "text", description = "The note's text", required = true }

[concept.AnnotatedExpenseReport]
description = "A report holding completions and notes"

[concept.AnnotatedExpenseReport.structure]
completions = { type = "list", item_type = "concept", item_concept_ref = "doc_gen_update.ExpenseCompletion", description = "Its completions" }
notes       = { type = "list", item_type = "concept", item_concept_ref = "doc_gen_update.ExpenseNote", description = "Its notes" }

[concept.ExpenseWorkbook]
description = "The caller's workbook with the categories filled in"
refines     = "Document"
"""


def _bundle(
    *, inputs: str = 'workbook = "Document", completions = "ExpenseCompletion[]"', template: str = 'template_input = "workbook"', step_fields: str
) -> str:
    return (
        _CONCEPTS
        + f"""
[pipe.complete_expenses]
type           = "PipeDocGen"
description    = "Write the categories into the workbook's rows"
inputs         = {{ {inputs} }}
output         = "ExpenseWorkbook"
format         = "xlsx"
{template}
table_fill     = "update"
{step_fields}
"""
    )


def _inputs(*, workbook_bytes: bytes) -> dict[str, Any]:
    url = f"data:{XLSX_MIME_TYPE};base64,{base64.b64encode(workbook_bytes).decode('ascii')}"
    return {
        "workbook": {"concept": "native.Document", "content": {"url": url, "mime_type": XLSX_MIME_TYPE, "filename": "expenses.xlsx"}},
        "completions": {
            "concept": "doc_gen_update.ExpenseCompletion",
            "content": [
                {"invoice_number": "INV-1", "row": 1, "category": "Travel"},
                {"invoice_number": "INV-2", "row": 2, "category": None},
            ],
        },
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
class TestPipeDocGenTableUpdate:
    @pytest.mark.parametrize(
        ("step_fields", "expected"),
        [
            ('match_on = ["invoice_number"]', (["invoice_number"], None, CellPolicy.FILL_EMPTY)),
            ('match_row = "row"\ncells = "overwrite"', (None, "row", CellPolicy.OVERWRITE)),
        ],
        ids=["by_key_filling_empty_cells_by_default", "by_row_overwriting"],
    )
    async def test_the_engine_and_its_checker_receive_the_update(
        self, updating_xlsx_stub_engines: StubEngines, step_fields: str, expected: tuple[list[str] | None, str | None, CellPolicy]
    ) -> None:
        """The job and both template checks, run setup's and the print's, carry the fill, the matching field and the policy."""
        workbook = xlsx_bytes()

        await PipelexMTHDSProtocol().execute(mthds_contents=[_bundle(step_fields=step_fields)], inputs=_inputs(workbook_bytes=workbook))

        (job,) = updating_xlsx_stub_engines.engine.jobs
        assert job.table_fill == TableFill.UPDATE
        assert (job.match_on, job.match_row, job.cells) == expected
        assert job.data["completions"][1] == {"invoice_number": "INV-2", "row": 2, "category": None}
        assert len(updating_xlsx_stub_engines.check_requests) == 2
        for request in updating_xlsx_stub_engines.check_requests:
            assert request.table_fill == TableFill.UPDATE
            assert (request.match_on, request.match_row, request.cells) == expected

    async def test_an_engine_that_only_appends_is_refused_when_the_method_loads(self, xlsx_stub_engines: StubEngines) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                mthds_contents=[_bundle(step_fields='match_on = ["invoice_number"]')], inputs=_inputs(workbook_bytes=xlsx_bytes())
            )

        item = only_problem_item(exc_info.value)
        assert item.code == CoreCode.MODEL_CAPABILITY_UNSUPPORTED
        assert item.params is not None
        assert item.params.model_dump(exclude_none=True) == {"model": "pipelex-xlsx", "capability": "table_update"}
        assert "asks the engine 'pipelex-xlsx' to update a Table's rows with records" in refusal_messages(exc_info.value)
        assert xlsx_stub_engines.engine.jobs == []

    @pytest.mark.parametrize(
        ("inputs", "step_fields", "expected_field", "expected_finding"),
        [
            (None, 'match_on = ["invoice_no"]', "match_on", "the records of 'completions' have no field 'invoice_no'"),
            (None, 'match_on = ["invoice_number", "amount"]', "match_on", "the records of 'completions' have no field 'amount'"),
            (None, 'match_row = "position"', "match_row", "the records of 'completions' have no field 'position' holding their row's position"),
            (None, 'match_row = "category"', "match_row", "the field 'category' of the records of 'completions' holds a row's position"),
            (
                'workbook = "Document", report = "ExpenseReport"',
                'match_on = ["invoice_no"]',
                "match_on",
                "the records of 'report.completions' have no field 'invoice_no'",
            ),
            (
                'workbook = "Document", note = "Text"',
                'match_on = ["invoice_number"]',
                "match_on",
                "none of the step's inputs holds a list of records",
            ),
            (
                'workbook = "Document", report = "AnnotatedExpenseReport"',
                'match_on = ["invoice_no"]',
                "match_on",
                (
                    "no list of records of the step's data carries every field the update matches rows by, so no Table could be updated: "
                    "the records of 'report.completions' have no field 'invoice_no'"
                ),
            ),
            (
                'workbook = "Document", report = "AnnotatedExpenseReport"',
                'match_row = "category"',
                "match_row",
                "the field 'category' of the records of 'report.completions' holds a row's position",
            ),
        ],
        ids=[
            "unknown_key",
            "one_unknown_key_of_two",
            "unknown_row_field",
            "text_row_field",
            "nested_list",
            "no_list_of_records",
            "no_list_of_two_carries_the_key",
            "the_list_carrying_the_field_holds_the_wrong_kind",
        ],
    )
    async def test_the_load_refuses_fields_the_records_do_not_carry(
        self,
        updating_xlsx_stub_engines: StubEngines,
        inputs: str | None,
        step_fields: str,
        expected_field: str,
        expected_finding: str,
    ) -> None:
        bundle = _bundle(step_fields=step_fields) if inputs is None else _bundle(inputs=inputs, step_fields=step_fields)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle])

        item = only_problem_item(exc_info.value)
        assert item.params is not None
        params = item.params.model_dump(exclude_none=True)
        assert params["field_path"] == f"pipe.complete_expenses.{expected_field}"
        assert expected_finding in params["finding"]
        assert updating_xlsx_stub_engines.engine.jobs == []

    async def test_a_nested_list_carrying_the_key_is_accepted(self, updating_xlsx_stub_engines: StubEngines) -> None:
        bundle = _bundle(inputs='workbook = "Document", report = "ExpenseReport"', step_fields='match_on = ["invoice_number"]')

        await validate_bundle(mthds_contents=[bundle])

        assert updating_xlsx_stub_engines.engine.jobs == []

    async def test_a_list_lacking_the_key_beside_one_carrying_it_is_accepted(self, updating_xlsx_stub_engines: StubEngines) -> None:
        """The report's notes fill no Table, so the load does not hold them to the key its completions carry."""
        bundle = _bundle(inputs='workbook = "Document", report = "AnnotatedExpenseReport"', step_fields='match_on = ["invoice_number"]')

        await validate_bundle(mthds_contents=[bundle])

        assert updating_xlsx_stub_engines.engine.jobs == []

    async def test_the_dry_run_hands_the_checker_no_mock_data_under_an_update(self, tmp_path: Path, updating_xlsx_stub_engines: StubEngines) -> None:
        """Mock records match no real row of the method's template, so the checker judges its structure alone."""
        (tmp_path / "expenses.xlsx").write_bytes(xlsx_bytes())
        (tmp_path / "METHODS.toml").write_text(METHOD_MANIFEST, encoding="utf-8")
        bundle_path = tmp_path / "complete_expenses.mthds"
        bundle_path.write_text(
            _bundle(
                inputs='completions = "ExpenseCompletion[]"', template='template_file  = "expenses.xlsx"', step_fields='match_on = ["invoice_number"]'
            ),
            encoding="utf-8",
        )

        await validate_bundle(mthds_file_path=bundle_path)

        assert updating_xlsx_stub_engines.check_requests
        for request in updating_xlsx_stub_engines.check_requests:
            assert request.table_fill == TableFill.UPDATE
            assert request.match_on == ["invoice_number"]
            assert request.data is None
