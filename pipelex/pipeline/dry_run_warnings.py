"""Advisory dry-run findings (`warnings`) for the validate surfaces.

A dry run can find something worth surfacing on a VALID bundle without failing: the first occupant is a
`PipeDocGen` step's template check, whose warning findings (`template_check_warning`) name a field of an
office template that matches no input, a Markdown field that would print its markup, and the like. A
sweep asked to collect them (`collect_dry_run_warnings`) keeps each pipe's findings on its `DryRunOutput`
(`pipelex.pipe_run.dry_run_warning_collector` explains how they get there), and this family projects them
into the report, so the map it reads must come from such a sweep.

Unlike the static lints, this family needs no bundle-wide view: a finding is about the step whose dry run
made it, so a surface that dry-runs a single pipe carries it too.
"""

from collections.abc import Mapping

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.pipeline.bundle_validator import DryRunOutput


def build_dry_run_warnings(dry_run_result: Mapping[str, DryRunOutput]) -> list[ValidationErrorItem]:
    """Project the sweep's per-pipe dry-run findings into advisory `warnings` items.

    One step is dry-run once for itself and once more inside every controller that runs it, and it finds the
    same thing each time, so a finding is kept once, at its first appearance in sweep order.

    Args:
        dry_run_result: The sweep's per-pipe status map (`ValidateBundleResult.dry_run_result`, or what
            `BundleValidator.validate_pipes` returned).

    Returns:
        The findings, deduplicated, in sweep order.
    """
    warnings: list[ValidationErrorItem] = []
    for dry_run_output in dry_run_result.values():
        for warning in dry_run_output.warnings:
            if warning not in warnings:
                warnings.append(warning)
    return warnings
