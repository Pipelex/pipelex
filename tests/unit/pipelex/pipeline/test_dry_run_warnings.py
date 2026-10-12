from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.dry_run_warnings import build_dry_run_warnings
from pipelex.validation_error_types import TemplateCheckErrorType


def _template_warning(*, pipe_code: str, message: str) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.DRY_RUN,
        error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
        pipe_code=pipe_code,
        domain_code="invoicing",
        template_file="invoice.xlsx",
        template_location="the defined name Totl",
        message=message,
    )


def _output(*, pipe_code: str, status: DryRunStatus, warnings: list[ValidationErrorItem]) -> DryRunOutput:
    return DryRunOutput(pipe_code=pipe_code, pipe_ref=f"invoicing.{pipe_code}", status=status, warnings=warnings)


class TestBuildDryRunWarnings:
    def test_a_sweep_with_no_findings_has_no_warnings(self) -> None:
        dry_run_result = {"invoicing.print_invoice": _output(pipe_code="print_invoice", status=DryRunStatus.SUCCESS, warnings=[])}

        assert build_dry_run_warnings(dry_run_result) == []

    def test_a_step_found_again_inside_its_controller_is_reported_once(self) -> None:
        """The step is dry-run for itself and inside the sequence that runs it, and finds the same thing both times."""
        name_warning = _template_warning(pipe_code="print_invoice", message="The name Totl matches no field")
        markup_warning = _template_warning(pipe_code="print_invoice", message="The cell B4 prints Markdown markup")
        dry_run_result = {
            "invoicing.print_invoice": _output(pipe_code="print_invoice", status=DryRunStatus.SUCCESS, warnings=[name_warning]),
            "invoicing.bill_customer": _output(pipe_code="bill_customer", status=DryRunStatus.SUCCESS, warnings=[name_warning, markup_warning]),
        }

        assert build_dry_run_warnings(dry_run_result) == [name_warning, markup_warning]

    def test_findings_keep_the_sweep_order_whatever_the_outcome(self) -> None:
        """A pipe allowed to fail, or skipped, still carries what its dry run found before it stopped."""
        first = _template_warning(pipe_code="print_quote", message="The shape Title is filled from a number")
        second = _template_warning(pipe_code="print_invoice", message="The name Totl matches no field")
        dry_run_result = {
            "invoicing.print_quote": _output(pipe_code="print_quote", status=DryRunStatus.FAILURE, warnings=[first]),
            "invoicing.print_invoice": _output(pipe_code="print_invoice", status=DryRunStatus.SUCCESS, warnings=[second]),
        }

        assert build_dry_run_warnings(dry_run_result) == [first, second]
