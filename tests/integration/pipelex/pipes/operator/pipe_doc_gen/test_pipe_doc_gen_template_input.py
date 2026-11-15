"""A PipeDocGen step that fills the workbook its run supplies, appending the step's records to the workbook's Table.

The run's caller sends the workbook as an input, the step's engine fills a copy of it, and the copy is the run's output,
stored as a new file named after the caller's. The workbook is checked before any step starts, by run setup, and again
by the print, before the engine fills it.
"""

import base64
from collections.abc import Iterator
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation import doc_gen_template_input
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.cogt.doc_gen.table_fill import TableFill
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenTemplateInputUnfitError
from pipelex.pipeline import doc_gen_template_inputs, execution_seams
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.uri.uri_bytes import UriBytes
from pipelex.validation_error_types import TemplateCheckErrorType
from tests.helpers.office_files import DOCX_MIME_TYPE, XLSX_MIME_TYPE, docx_bytes, xlsx_bytes
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, only_problem_item, refusal_messages
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_APPEND_MTHDS = """
domain = "doc_gen_append"
description = "Recording expenses in the caller's workbook"
main_pipe = "append_expenses"

[concept.ExpenseRow]
description = "One expense"

[concept.ExpenseRow.structure]
description = { type = "text", description = "What was bought", required = true }
amount      = { type = "number", description = "The amount, in euros", required = true }

[concept.ExpenseWorkbook]
description = "The caller's workbook with the expenses recorded"
refines     = "Document"

[pipe.append_expenses]
type           = "PipeDocGen"
description    = "Append the expenses to the workbook's Table"
inputs         = { workbook = "Document", expense_rows = "ExpenseRow[]" }
output         = "ExpenseWorkbook"
format         = "xlsx"
template_input = "workbook"
table_fill     = "append"
"""

_TEMPLATE_CHECK_LOG_LINE = "The template check of a PipeDocGen found a warning in its template file"


def _data_url(*, mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def _inputs(*, workbook_bytes: bytes, mime_type: str = XLSX_MIME_TYPE) -> dict[str, Any]:
    url = _data_url(mime_type=mime_type, raw_bytes=workbook_bytes)
    return _inputs_with_workbook(workbook_content={"url": url, "mime_type": mime_type, "filename": "expenses.xlsx"})


def _inputs_with_workbook(*, workbook_content: dict[str, str]) -> dict[str, Any]:
    return {
        "workbook": {"concept": "native.Document", "content": workbook_content},
        "expense_rows": {
            "concept": "doc_gen_append.ExpenseRow",
            "content": [{"description": "Tea", "amount": 7.0}, {"description": "Cake", "amount": 4.5}],
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
class TestPipeDocGenTemplateInput:
    async def test_the_engine_fills_the_caller_s_workbook_and_the_copy_is_stored_under_its_name(self, xlsx_stub_engines: StubEngines) -> None:
        """The job carries the workbook's bytes and the fill, the data holds only the records, and the output is named after the input."""
        workbook = xlsx_bytes()

        result = await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=workbook))

        (job,) = xlsx_stub_engines.engine.jobs
        assert job.template == workbook
        assert job.template_name == "the input 'workbook'"
        assert job.table_fill == TableFill.APPEND
        assert job.data is not None
        assert list(job.data) == ["expense_rows"]
        assert job.data["expense_rows"] == [{"description": "Tea", "amount": 7.0}, {"description": "Cake", "amount": 4.5}]
        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename == "expenses.xlsx"
        # Checked by run setup, then by the print before the engine fills it, each time against the records' shape alone.
        assert [request.template for request in xlsx_stub_engines.check_requests] == [workbook, workbook]
        assert all(list(request.inputs) == ["expense_rows"] for request in xlsx_stub_engines.check_requests)

    async def test_a_workbook_the_check_finds_unfit_refuses_the_run_before_any_step_starts(self, xlsx_stub_engines: StubEngines) -> None:
        xlsx_stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The workbook holds no Table")]

        with pytest.raises(PipeDocGenTemplateInputUnfitError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.DOCGEN_TEMPLATE_INPUT_UNFIT
        assert "The workbook holds no Table" in exc_info.value.message
        assert "the input 'workbook'" in exc_info.value.message
        assert xlsx_stub_engines.engine.jobs == []
        assert len(xlsx_stub_engines.check_requests) == 1

    async def test_a_warning_on_the_workbook_is_logged_and_the_run_proceeds(self, xlsx_stub_engines: StubEngines, mocker: MockerFixture) -> None:
        warning_spy = mocker.spy(log, "warning")
        xlsx_stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.WARNING, message="The Table has a totals row")]

        await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        assert len(xlsx_stub_engines.engine.jobs) == 1
        logged = [call.kwargs["fields"] for call in warning_spy.call_args_list if call.args and call.args[0] == _TEMPLATE_CHECK_LOG_LINE]
        assert logged
        assert all(fields["template_file"] == "the input 'workbook'" for fields in logged)
        assert all(fields["finding_message"] == "The Table has a totals row" for fields in logged)

    async def test_a_word_document_given_as_the_workbook_is_refused_as_the_caller_s_input(self, xlsx_stub_engines: StubEngines) -> None:
        """The bytes decide, so a Word document declared and named as a workbook is refused before any engine sees it."""
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=docx_bytes()))

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
        assert "workbook" in exc_info.value.message
        assert xlsx_stub_engines.engine.jobs == []
        assert xlsx_stub_engines.check_requests == []

    async def test_a_word_document_declared_as_word_is_refused_too(self, xlsx_stub_engines: StubEngines) -> None:
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=docx_bytes(), mime_type=DOCX_MIME_TYPE)
            )

        assert exc_info.value.to_problem(view=ProblemView.CALLER).code == CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
        assert xlsx_stub_engines.engine.jobs == []

    @pytest.mark.usefixtures("replace_only_xlsx_stub_engines")
    async def test_an_engine_that_does_not_declare_appending_is_refused_when_the_method_loads(self) -> None:
        """The caller reads the model and the capability it lacks; the operator reads the fill the step asks for."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        item = only_problem_item(exc_info.value)
        assert item.code == CoreCode.MODEL_CAPABILITY_UNSUPPORTED
        assert item.params is not None
        assert item.params.model_dump(exclude_none=True) == {"model": "pipelex-xlsx", "capability": "table_append"}
        assert "asks the engine 'pipelex-xlsx' to append records to a Table" in refusal_messages(exc_info.value)

    async def test_validation_says_the_workbook_is_checked_when_a_run_supplies_it(self, xlsx_stub_engines: StubEngines) -> None:
        report = await validate_bundles_in_process(mthds_contents=[_APPEND_MTHDS])

        assert report.is_valid is True
        template_warnings = [warning for warning in report.warnings if warning.error_type == TemplateCheckErrorType.TEMPLATE_CHECK_WARNING]
        assert template_warnings
        assert all("checked against the step's inputs when a run supplies it" in warning.message for warning in template_warnings)
        assert all(warning.template_file == "the input 'workbook'" for warning in template_warnings)
        assert xlsx_stub_engines.check_requests == []

    @pytest.mark.parametrize("where", ["https_declared_as_pdf", "stored_named_as_word"])
    async def test_a_workbook_labelled_as_another_format_passes_setup_on_its_bytes(
        self, xlsx_stub_engines: StubEngines, mocker: MockerFixture, where: str
    ) -> None:
        """Run setup's generic format check reads the label, so it leaves a template to the check that reads the bytes."""
        workbook = xlsx_bytes()
        workbook_content: dict[str, str]
        match where:
            case "https_declared_as_pdf":
                mocker.patch.object(
                    doc_gen_template_input, "load_bytes_and_mime_type_from_any_uri", return_value=UriBytes(data=workbook, mime_type="application/pdf")
                )
                workbook_content = {"url": "https://files.example.com/expenses", "mime_type": "application/pdf"}
            case _:
                url = await get_storage_provider().store(data=workbook, key="template-input-tests/expenses.docx")
                workbook_content = {"url": url, "filename": "expenses.docx"}

        pipe_job, _pipeline_run_id, _ = await pipeline_run_setup(
            storage_scope="template-input-tests",
            read_scope=None,
            user_id="test-user",
            execution_config=get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False),
            mthds_contents=[_APPEND_MTHDS],
            pipe_code="append_expenses",
            inputs=_inputs_with_workbook(workbook_content=workbook_content),
        )

        assert pipe_job.pipe.code == "append_expenses"
        assert [request.template for request in xlsx_stub_engines.check_requests] == [workbook]

    async def test_setup_checks_the_step_the_walk_reached_whatever_its_library_key(
        self, xlsx_stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        """A step whose reference is not its library key, as a dependency package's is not, is still checked at setup.

        The entry step is handed to the check under a code the library does not hold, so a lookup by its reference finds
        nothing: the check must use the step the walk reached, and refuse the run before any step starts.
        """
        real_check = doc_gen_template_inputs.check_doc_gen_template_inputs

        async def _check_with_an_unkeyed_step(*, entry_pipe: PipeAbstract, working_memory: WorkingMemory, read_scope: str | None) -> None:
            await real_check(
                entry_pipe=entry_pipe.model_copy(update={"code": "kept_under_another_key"}), working_memory=working_memory, read_scope=read_scope
            )

        mocker.patch.object(execution_seams, "check_doc_gen_template_inputs", side_effect=_check_with_an_unkeyed_step)
        setup_checker_spy = mocker.spy(doc_gen_template_inputs, "check_office_template")
        xlsx_stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The workbook holds no Table")]

        with pytest.raises(PipeDocGenTemplateInputUnfitError):
            await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        assert setup_checker_spy.call_count == 1
        assert xlsx_stub_engines.engine.jobs == []

    async def test_the_print_checks_the_workbook_with_the_worker_it_fills_it_with(self, xlsx_stub_engines: StubEngines) -> None:
        """Run setup builds a worker for its check, and the print one worker for both its check and its fill."""
        await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        assert len(xlsx_stub_engines.check_requests) == 2
        assert xlsx_stub_engines.nb_builds == 2

    async def test_a_checker_that_fails_on_the_caller_s_workbook_refuses_it_as_the_caller_s(
        self, xlsx_stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        """An exception the engine's checker did not mean is still the template's refusal, never an unexpected failure."""
        mocker.patch.object(xlsx_stub_engines, "check_template", side_effect=KeyError("Table1"))

        with pytest.raises(DocGenRenderError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[_APPEND_MTHDS], inputs=_inputs(workbook_bytes=xlsx_bytes()))

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.DOCGEN_TEMPLATE_INPUT_UNFIT
        assert problem.params is not None
        assert problem.params.model_dump(exclude_none=True) == {"input": "workbook", "finding": "the engine's template check failed on the file"}
        assert "Table1" in exc_info.value.message
        assert xlsx_stub_engines.engine.jobs == []

    async def test_a_checker_that_fails_on_the_method_s_template_file_refuses_it_as_the_method_s(
        self, stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(stub_engines, "check_template", side_effect=KeyError("invoice.total"))

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "docx"\ntemplate_file = "templates/invoice.docx"')],
                submitted_files={"templates/invoice.docx": b"PK docx template bytes"},
            )

        item = only_problem_item(exc_info.value)
        assert item.code == PipelexErrorCode.DOCGEN_TEMPLATE_INVALID
        assert item.params is not None
        assert item.params.model_dump(exclude_none=True) == {
            "template": "templates/invoice.docx",
            "reason": "check_failed",
            "finding": "the engine's template check failed on the file",
        }
