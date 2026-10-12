import asyncio

import pytest

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.pipe_run.dry_run_warning_collector import collecting_dry_run_warnings, report_dry_run_warning
from pipelex.validation_error_types import TemplateCheckErrorType


def _template_warning(*, message: str) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.DRY_RUN,
        error_type=TemplateCheckErrorType.TEMPLATE_CHECK_WARNING,
        pipe_code="print_invoice",
        domain_code="invoicing",
        template_file="invoice.xlsx",
        message=message,
    )


class TestDryRunWarningCollector:
    def test_a_warning_outside_a_sweep_is_not_taken(self) -> None:
        assert report_dry_run_warning(warning=_template_warning(message="The name Totl matches no field")) is False

    def test_a_sweep_keeps_each_warning_once_in_the_order_found(self) -> None:
        first = _template_warning(message="The name Totl matches no field")
        second = _template_warning(message="The cell B4 prints Markdown markup")

        with collecting_dry_run_warnings() as collector:
            assert report_dry_run_warning(warning=first) is True
            assert report_dry_run_warning(warning=second) is True
            assert report_dry_run_warning(warning=first) is True

        assert collector.warnings == [first, second]

    def test_the_scope_ends_with_the_sweep(self) -> None:
        with collecting_dry_run_warnings():
            pass

        assert report_dry_run_warning(warning=_template_warning(message="The name Totl matches no field")) is False

    def test_nested_scopes_keep_their_own_warnings(self) -> None:
        outer_warning = _template_warning(message="Found by the outer dry run")
        inner_warning = _template_warning(message="Found by the inner dry run")

        with collecting_dry_run_warnings() as outer:
            report_dry_run_warning(warning=outer_warning)
            with collecting_dry_run_warnings() as inner:
                report_dry_run_warning(warning=inner_warning)

        assert outer.warnings == [outer_warning]
        assert inner.warnings == [inner_warning]

    @pytest.mark.asyncio
    async def test_the_tasks_of_a_fan_out_report_to_the_sweep(self) -> None:
        """A batch or a parallel step runs its pipes as asyncio tasks, which copy the context they were made in."""
        warnings = [_template_warning(message=f"Found by branch {branch_index}") for branch_index in range(3)]

        async def report(warning: ValidationErrorItem) -> bool:
            await asyncio.sleep(0)
            return report_dry_run_warning(warning=warning)

        with collecting_dry_run_warnings() as collector:
            taken = await asyncio.gather(*(asyncio.create_task(report(warning)) for warning in warnings))

        assert taken == [True, True, True]
        assert sorted(warning.message for warning in collector.warnings) == sorted(warning.message for warning in warnings)
