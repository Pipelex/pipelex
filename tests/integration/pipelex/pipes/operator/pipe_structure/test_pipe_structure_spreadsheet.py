import base64
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest
from mthds.protocol.problem.registry import CoreCode, MethodOutputMultiplicityMismatchExpected
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure import pipe_structure as pipe_structure_module
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.tabular.exceptions import CsvCoercionError, TableFileTypeUnsupportedError
from pipelex.validation_error_types import PipeValidationErrorType
from tests.helpers.xlsx_workbooks import sheet_workbook, single_table_workbook

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

[concept.Filing]
description = "A filing that holds a document among its fields, without being one"
[concept.Filing.structure]
attachment = {{ type = "concept", concept_ref = "native.Document", description = "The attached document" }}
label      = {{ type = "text", description = "A label" }}

[concept]
Note = "A note with no structure"
Workbook = {{ description = "A budget workbook", refines = "Document" }}
SignedWorkbook = {{ description = "A signed budget workbook", refines = "budget_read.Workbook" }}
Photo = {{ description = "A photo of a receipt", refines = "Image" }}
"""


def _structure_pipe(
    *,
    inputs: dict[str, str] | None = None,
    output: str = "BudgetLine[]",
    table: str | None = None,
    sheet_range: dict[str, Any] | None = None,
    row_field: str | None = "line",
    model: str | None = None,
) -> PipeStructure:
    blueprint_fields: dict[str, Any] = {"model": model} if model is not None else {}
    if sheet_range is not None:
        blueprint_fields["sheet_range"] = sheet_range
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
        concept_codes_from_the_same_domain=["BudgetLine", "Filing", "Folder", "Note", "Photo", "SignedWorkbook", "Workbook"],
    )


def _data_url(*, data: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


async def _run(
    *,
    pipe: PipeStructure,
    document: DocumentContent,
    job_metadata: JobMetadata,
    pipe_run_mode: PipeRunMode,
    output_multiplicity: VariableMultiplicity | None = None,
) -> list[StuffContent]:
    document_stuff = StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.DOCUMENT), content=document, name="budget")
    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode, output_multiplicity=output_multiplicity),
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

    def test_a_concept_refining_document_at_any_depth_reads_a_spreadsheet(self) -> None:
        pipe = _structure_pipe(inputs={"budget": "SignedWorkbook"})

        pipe.validate_inputs_with_library()
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
            pytest.param({"inputs": {"text": "Text"}, "sheet_range": {}}, "inputs", "sheet_range", None, id="sheet-range-on-text-path"),
            pytest.param({"inputs": {"text": "Text"}}, "inputs", "row_field", None, id="row-field-on-text-path"),
            pytest.param({"inputs": {"picture": "Image"}}, "inputs", None, PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH, id="image-input"),
            # A concept holding a Document in a field is no Document: only lineage makes the input a spreadsheet.
            pytest.param(
                {"inputs": {"filing": "Filing"}}, "inputs", None, PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH, id="document-in-a-field"
            ),
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

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_range_on_a_sheet_is_read_into_the_output_list(self, job_metadata: JobMetadata) -> None:
        cells = {"A1": "Budget 2026", "A3": "Item", "B3": "Amount", "A4": "Paper", "B4": 12.5, "A5": "Ink", "B5": 3, "B6": "=SUM(B4:B5)"}
        workbook = sheet_workbook(cells=cells, sheet_title="Budget")
        document = DocumentContent(url=_data_url(data=workbook, mime_type=XLSX_MIME), mime_type=XLSX_MIME, filename="budget.xlsx")

        pipe = _structure_pipe(sheet_range={"sheet": "budget", "header_row": 3})
        items = await _run(pipe=pipe, document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE)

        assert [item.model_dump(include={"item", "amount", "line"}) for item in items] == [
            {"item": "Paper", "amount": 12.5, "line": 1},
            {"item": "Ink", "amount": 3, "line": 2},
        ]

    @pytest.mark.asyncio(loop_scope="class")
    async def test_rows_of_formulas_storing_no_value_are_not_read_and_warned_of(self, job_metadata: JobMetadata, mocker: MockerFixture) -> None:
        """A workbook saved without its calculated values: rows of formulas may hold data nobody calculated."""
        cells = {"A1": "Item", "B1": "Amount", "A2": "=Source!A2", "B2": "=Source!B2", "A3": "=Source!A3", "B3": "=Source!B3"}
        workbook = sheet_workbook(cells=cells, sheet_title="Budget")
        document = DocumentContent(url=_data_url(data=workbook, mime_type=XLSX_MIME), mime_type=XLSX_MIME, filename="budget.xlsx")
        warning = mocker.patch.object(pipe_structure_module.log, "warning")

        pipe = _structure_pipe(sheet_range={"sheet": "budget"})
        items = await _run(pipe=pipe, document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE)

        assert items == []
        warning.assert_called_once()
        assert warning.call_args.args == ("Rows of uncalculated formulas were not read",)
        assert warning.call_args.kwargs["fields"]["nb_rows"] == 2
        assert warning.call_args.kwargs["fields"]["user_action"].startswith("Open the workbook in Excel or LibreOffice and save it")

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

    @pytest.mark.parametrize(
        ("output_multiplicity", "expected"),
        [
            pytest.param(False, MethodOutputMultiplicityMismatchExpected.SINGLE, id="single-output"),
            pytest.param(3, MethodOutputMultiplicityMismatchExpected.FIXED, id="fixed-count"),
        ],
    )
    @pytest.mark.parametrize("pipe_run_mode", [PipeRunMode.LIVE, PipeRunMode.DRY])
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_run_asking_for_another_multiplicity_is_refused(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        output_multiplicity: VariableMultiplicity,
        expected: MethodOutputMultiplicityMismatchExpected,
    ) -> None:
        """The table decides how many records the step outputs, so a step's `nb_output` or `multiple_output = false` cannot be honoured."""
        csv_bytes = b"item,amount\nPaper,2\n"
        document = DocumentContent(url=_data_url(data=csv_bytes, mime_type="text/csv"), mime_type="text/csv", filename="budget.csv")

        with pytest.raises(PipeRouterError) as exc_info:
            await _run(
                pipe=_structure_pipe(),
                document=document,
                job_metadata=job_metadata,
                pipe_run_mode=pipe_run_mode,
                output_multiplicity=output_multiplicity,
            )

        cause = exc_info.value.__cause__
        assert isinstance(cause, PipeRunError)
        assert "remove the step's `nb_output` or `multiple_output`" in str(cause)
        wire = cause.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.METHOD_OUTPUT_MULTIPLICITY_MISMATCH
        assert wire.get("params") == {"pipe": "read_budget", "declared": "list", "expected": expected}, wire

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_run_asking_for_a_list_reads_the_table(self, job_metadata: JobMetadata) -> None:
        csv_bytes = b"item,amount\nPaper,2\n"
        document = DocumentContent(url=_data_url(data=csv_bytes, mime_type="text/csv"), mime_type="text/csv", filename="budget.csv")

        items = await _run(
            pipe=_structure_pipe(), document=document, job_metadata=job_metadata, pipe_run_mode=PipeRunMode.LIVE, output_multiplicity=True
        )

        assert [item.model_dump()["item"] for item in items] == ["Paper"]
