from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.validate._validate_core import validate_bundle_core, validate_pipe_core
from pipelex.cli.commands.validate._validate_core import _validate_pipe_or_bundle  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipe_run.dry_run_in_process import dry_run_pipe_in_process
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.pipeline.validation_render import format_validate_markdown
from pipelex.validation_error_types import TemplateCheckErrorType
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, write_bundle

if TYPE_CHECKING:
    from pytest_mock import MockType

_DOCX_TEMPLATE_STEP = 'format = "docx"\ntemplate_file = "invoice.docx"'
_TEMPLATE_CHECK_LOG_LINE = "The template check of a PipeDocGen found a warning in its template file"

_NOTES_FINDING = TemplateFinding(
    severity=TemplateFindingSeverity.WARNING, message="The notes are never printed", location="the field notes on page 2"
)
_NOTES_WARNING = ValidationErrorItem(
    category=ValidationErrorCategory.DRY_RUN,
    error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
    pipe_code="print_invoice",
    domain_code="doc_gen_tests",
    template_file="invoice.docx",
    template_location="the field notes on page 2",
    message="PipeDocGen 'print_invoice', template file 'invoice.docx': The notes are never printed (the field notes on page 2)",
)

# A bundle of another domain whose sequence runs the templated step, which a library directory holds: the step is
# dry-run only inside the sequence, so its warning reaches the verdict from a pipe the sweep did not sweep itself.
_CALLER_MTHDS = """
domain = "doc_gen_caller"
description = "Billing a customer with a printed invoice"
main_pipe = "bill_customer"

[pipe.bill_customer]
type        = "PipeSequence"
description = "Print the customer's invoice"
inputs      = { invoice = "doc_gen_tests.Invoice" }
output      = "doc_gen_tests.InvoicePdf"
steps       = [{ pipe = "doc_gen_tests.print_invoice", result = "invoice_pdf" }]
"""


@pytest.fixture(autouse=True)
def restore_the_outer_library() -> Iterator[None]:
    """Tear down whatever library a channel left current, and restore the one the test started in.

    `validate_bundle` leaves its validation library open on success, and the bare CLI leaves the library it loaded
    current for the command that owns `Pipelex` teardown. Called directly, both leak into the next test.
    """
    outer_library_id = get_current_library_id_or_none()
    yield
    leaked_library_id = get_current_library_id_or_none()
    if leaked_library_id is not None and leaked_library_id != outer_library_id:
        get_library_manager().teardown(library_id=leaked_library_id)
    if outer_library_id is not None:
        set_current_library(library_id=outer_library_id)
    else:
        clear_current_library()


def _write_templated_bundle(*, directory: Path, stub_engines: StubEngines) -> Path:
    (directory / "invoice.docx").write_bytes(b"docx bytes")
    stub_engines.findings = [_NOTES_FINDING]
    return write_bundle(directory=directory, step_fields=_DOCX_TEMPLATE_STEP)


def _template_check_log_calls(warning_spy: "MockType") -> list[dict[str, Any]]:
    return [call.kwargs["fields"] for call in warning_spy.call_args_list if call.args and call.args[0] == _TEMPLATE_CHECK_LOG_LINE]


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenTemplateWarnings:
    async def test_the_protocol_report_carries_a_warning_found_inside_a_sequence(
        self, tmp_path: Path, stub_engines: StubEngines, mocker: MockerFixture
    ) -> None:
        """The report every backend returns, the runner's `/v1/validate` included, carries the warning once and stays valid.

        The graph arm dry-runs the sequence again and finds the warning again, and drops it rather than logging it.
        """
        warning_spy = mocker.spy(log, "warning")
        _write_templated_bundle(directory=tmp_path, stub_engines=stub_engines)

        report = await validate_bundles_in_process(mthds_contents=[_CALLER_MTHDS], library_dirs=[tmp_path])

        assert report.is_valid is True
        assert report.is_runnable is True
        assert [warning for warning in report.warnings if warning.error_type == TemplateCheckErrorType.TEMPLATE_CHECK_WARNING] == [_NOTES_WARNING]
        # Once in the sweep's dry run of the sequence, once more in the graph arm's.
        assert len(stub_engines.check_requests) == 2
        assert _template_check_log_calls(warning_spy) == []

    async def test_the_agent_cli_bundle_envelope_carries_the_warning(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        bundle_path = _write_templated_bundle(directory=tmp_path, stub_engines=stub_engines)

        result = await validate_bundle_core(bundle_path=bundle_path)

        assert result["is_valid"] is True
        assert result["warnings"] == [_NOTES_WARNING.model_dump(exclude_none=True)]
        assert f"- **{TemplateCheckErrorType.TEMPLATE_CHECK_WARNING}** — {_NOTES_WARNING.message}" in format_validate_markdown(result)

    async def test_the_agent_cli_pipe_envelope_carries_the_warning(self, tmp_path: Path, stub_engines: StubEngines) -> None:
        """`validate pipe` carries no bundle-wide lint, but what its dry run found is about the pipe it validated."""
        _write_templated_bundle(directory=tmp_path, stub_engines=stub_engines)

        result = await validate_pipe_core(pipe_code="print_invoice", library_dirs=[tmp_path])

        assert result["is_valid"] is True
        assert result["warnings"] == [_NOTES_WARNING.model_dump(exclude_none=True)]

    @pytest.mark.parametrize("target", ["bundle", "pipe"])
    async def test_the_bare_cli_echoes_the_warning(
        self, tmp_path: Path, stub_engines: StubEngines, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], target: str
    ) -> None:
        """Both bare-CLI targets echo the warning once, in yellow beside the verdict, and log nothing more."""
        warning_spy = mocker.spy(log, "warning")
        bundle_path = _write_templated_bundle(directory=tmp_path, stub_engines=stub_engines)

        match target:
            case "bundle":
                await _validate_pipe_or_bundle(bundle_path=bundle_path)
            case _:
                await _validate_pipe_or_bundle(pipe_code="print_invoice", library_dirs=[tmp_path])

        echoed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Warning: ")]
        assert echoed == [f"Warning: {_NOTES_WARNING.message}"]
        assert _template_check_log_calls(warning_spy) == []

    async def test_a_dry_run_no_sweep_collects_logs_the_warning(self, tmp_path: Path, stub_engines: StubEngines, mocker: MockerFixture) -> None:
        """Outside a validation sweep, as on `pipelex run --dry-run`, there is no verdict to carry the warning, so it is logged.

        The line is the same for every finding, and the finding's own words and place ride as fields beside the step and its file.
        """
        bundle_path = _write_templated_bundle(directory=tmp_path, stub_engines=stub_engines)
        result = await validate_bundle(mthds_file_path=bundle_path)
        (pipe,) = result.pipes
        warning_spy = mocker.spy(log, "warning")

        await dry_run_pipe_in_process(pipe, library_id=get_current_library())

        assert _template_check_log_calls(warning_spy) == [
            {
                "pipe_code": "print_invoice",
                "template_file": "invoice.docx",
                "finding_message": "The notes are never printed",
                "finding_location": "the field notes on page 2",
            }
        ]
