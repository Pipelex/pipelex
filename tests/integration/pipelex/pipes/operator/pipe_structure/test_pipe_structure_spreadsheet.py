import base64
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.tabular.exceptions import CsvCoercionError, TableFileTypeUnsupportedError
from pipelex.validation_error_types import PipeValidationErrorType
from tests.helpers.xlsx_workbooks import single_table_workbook

DOMAIN = "budget_read"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_BUNDLE = f"""\
domain = "{DOMAIN}"
description = "Read a budget workbook into lines"

[concept.BudgetLine]
description = "One line of a budget"
[concept.BudgetLine.structure]
line     = {{ type = "integer", description = "The line's position in the table" }}
item     = {{ type = "text", required = true, description = "What is bought" }}
amount   = {{ type = "number", description = "What it costs" }}
approved = {{ type = "boolean", description = "Whether it is approved" }}
due      = {{ type = "date", description = "When it is due" }}
label    = {{ type = "text", description = "A label" }}

[concept.Folder]
description = "A folder of lines"
[concept.Folder.structure]
lines = {{ type = "list", item_type = "text", description = "The lines" }}

[concept]
Note = "A note with no structure"
Workbook = {{ description = "A budget workbook", refines = "Document" }}
Photo = {{ description = "A photo of a receipt", refines = "Image" }}
"""


def _structure_pipe(
    *,
    inputs: dict[str, str] | None = None,
    output: str = "BudgetLine[]",
    table: str | None = None,
    row_field: str | None = "line",
    model: str | None = None,
) -> PipeStructure:
    blueprint_fields: dict[str, Any] = {"model": model} if model is not None else {}
    blueprint = PipeStructureBlueprint(
        description="Read the budget lines",
        inputs=inputs or {"budget": "Workbook"},
        output=output,
        table=table,
        row_field=row_field,
        **blueprint_fields,
    )
    return PipeFactory[PipeStructure].make_from_blueprint(
        domain_code=DOMAIN,
        pipe_code="read_budget",
        blueprint=blueprint,
        concept_codes_from_the_same_domain=["BudgetLine", "Folder", "Note", "Photo", "Workbook"],
    )


def _data_url(*, data: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


async def _run(*, pipe: PipeStructure, document: DocumentContent, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode) -> list[StuffContent]:
    document_stuff = StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.DOCUMENT), content=document, name="budget")
    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        job_metadata=job_metadata,
        working_memory=WorkingMemoryFactory.make_from_single_stuff(document_stuff),
        output_name="lines",
    )
    pipe_output = await get_pipe_router().run(pipe_job=pipe_job)
    return pipe_output.main_stuff_as_list(item_type=StuffContent).items


class TestPipeStructureSpreadsheet:
    @pytest.fixture(autouse=True)
    def _budget_library(self, tmp_path: Path, load_test_library: Callable[[list[Path]], None]) -> None:
        (tmp_path / "budget.mthds").write_text(_BUNDLE, encoding="utf-8")
        load_test_library([tmp_path])

    def test_a_valid_spreadsheet_step_passes_validation(self) -> None:
        pipe = _structure_pipe(table="Budget")

        pipe.validate_inputs_with_library()
        pipe.validate_output_with_library()
        assert pipe.reads_document()

    @pytest.mark.parametrize(
        ("pipe_fields", "validation", "expected_field", "expected_error_type"),
        [
            pytest.param({"model": "$writing-factual"}, "inputs", "model", None, id="model-refused"),
            pytest.param({"output": "BudgetLine"}, "output", None, PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY, id="single-output"),
            pytest.param({"output": "BudgetLine[3]"}, "output", None, PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY, id="fixed-count"),
            pytest.param({"output": "Note[]"}, "output", None, PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT, id="text-concept"),
            pytest.param({"output": "Photo[]"}, "output", "output", None, id="concept-without-fields"),
            pytest.param({"output": "Dynamic[]"}, "output", None, PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT, id="dynamic-concept"),
            pytest.param({"output": "Folder[]"}, "output", "output", None, id="nested-field"),
            pytest.param({"row_field": "missing"}, "output", "row_field", None, id="row-field-not-a-field"),
            pytest.param({"row_field": "label"}, "output", "row_field", None, id="row-field-not-a-number"),
            pytest.param({"inputs": {"text": "Text"}, "table": "Budget"}, "inputs", "table", None, id="table-on-text-path"),
            pytest.param({"inputs": {"text": "Text"}}, "inputs", "row_field", None, id="row-field-on-text-path"),
            pytest.param({"inputs": {"picture": "Image"}}, "inputs", None, PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH, id="image-input"),
        ],
    )
    def test_spreadsheet_rules_are_refused(
        self,
        pipe_fields: dict[str, Any],
        validation: str,
        expected_field: str | None,
        expected_error_type: PipeValidationErrorType | None,
    ) -> None:
        pipe = _structure_pipe(**pipe_fields)

        validate = pipe.validate_inputs_with_library if validation == "inputs" else pipe.validate_output_with_library
        with pytest.raises(PipeValidationError) as exc_info:
            validate()

        if expected_field is not None:
            assert exc_info.value.given_params.get("field_path") == f"pipe.read_budget.{expected_field}"
        if expected_error_type is not None:
            assert exc_info.value.error_type == expected_error_type

    @pytest.mark.parametrize("pipe_run_mode", [PipeRunMode.LIVE, PipeRunMode.DRY])
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_workbook_table_is_read_into_the_output_list(self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode) -> None:
        workbook = single_table_workbook(
            header=["Item", "Amount", "Approved", "Due", "Comment"],
            rows=[["Paper", 12.5, True, date(2026, 3, 4), "ignored"], ["Ink", None, None, None, None]],
            table_name="Budget",
        )
        document = DocumentContent(url=_data_url(data=workbook, mime_type=XLSX_MIME), mime_type=XLSX_MIME, filename="budget.xlsx")

        items = await _run(pipe=_structure_pipe(table="budget"), document=document, job_metadata=job_metadata, pipe_run_mode=pipe_run_mode)

        if pipe_run_mode.is_dry:
            # A dry run reads nothing: mock rows, each with its position.
            assert [item.model_dump()["line"] for item in items] == list(range(1, len(items) + 1))
            return
        assert [item.model_dump() for item in items] == [
            {"line": 1, "item": "Paper", "amount": 12.5, "approved": True, "due": date(2026, 3, 4), "label": None},
            {"line": 2, "item": "Ink", "amount": None, "approved": None, "due": None, "label": None},
        ]

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_csv_file_is_read_by_the_standard_conversions(self, job_metadata: JobMetadata) -> None:
        csv_bytes = b"item,amount,approved,due\nPaper,12.5,yes,2026-03-04\n\nInk,,no,\n"
        document = DocumentContent(url=_data_url(data=csv_bytes, mime_type="text/csv"), mime_type="text/csv", filename="budget.csv")

        items = await _run(pipe=_structure_pipe(), document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE)

        assert [item.model_dump() for item in items] == [
            {"line": 1, "item": "Paper", "amount": 12.5, "approved": True, "due": date(2026, 3, 4), "label": None},
            {"line": 2, "item": "Ink", "amount": None, "approved": False, "due": None, "label": None},
        ]

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_value_the_standard_refuses_names_the_row_and_the_field(self, job_metadata: JobMetadata) -> None:
        csv_bytes = b'item,amount\nPaper,"1,5"\n'
        document = DocumentContent(url=_data_url(data=csv_bytes, mime_type="text/csv"), mime_type="text/csv", filename="budget.csv")

        with pytest.raises(PipeRouterError) as exc_info:
            await _run(pipe=_structure_pipe(), document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE)

        assert isinstance(exc_info.value.__cause__, CsvCoercionError)
        message = str(exc_info.value.__cause__)
        assert "data row 1 (row 2)" in message
        assert "field amount" in message

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_pdf_document_is_refused_naming_the_input(self, job_metadata: JobMetadata) -> None:
        pdf_bytes = Path("tests/data/documents/solar_system.pdf").read_bytes()
        document = DocumentContent(url=_data_url(data=pdf_bytes, mime_type="application/pdf"), mime_type="application/pdf", filename="budget.pdf")

        with pytest.raises(PipeRouterError) as exc_info:
            await _run(pipe=_structure_pipe(), document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE)

        assert isinstance(exc_info.value.__cause__, TableFileTypeUnsupportedError)
        assert "Input 'budget' is a PDF document" in str(exc_info.value.__cause__)
