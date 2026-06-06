"""Render the end-of-run cost report from usage assembled on the pipeline output.

The cost report is sourced from the ``tokens_usages`` list that rides back on ``PipeOutput``
(assembled from the trace-event stream at the end of the run), not from a live per-process
registry. Both the main and agent CLIs call this so the two output channels behave identically.
"""

from collections.abc import Sequence
from pathlib import Path

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.tools.misc.file_utils import ensure_path, get_incremental_file_path


def render_run_cost_report(
    *,
    pipeline_run_id: str,
    tokens_usages: Sequence[AnyTokensUsage] | None,
    is_generate_costs: bool,
) -> None:
    """Render the cost report from a run's assembled token usage.

    No-op unless cost collection was on (``is_generate_costs``), the run actually assembled usage
    (``tokens_usages`` is a non-empty list), AND the total cost is non-zero. The zero-cost guard
    suppresses the report for dry runs (which emit zero-token synthetic usage) and any run with no
    priced usage — a dry run that somehow incurred real cost would still be reported. The two channels
    follow D6, each applied only when costs are on:

    - console (Rich table): gated by ``reporting_config.is_log_costs_to_console``
    - CSV file: gated by ``reporting_config.is_generate_cost_report_file_enabled``

    A cost-report failure never fails an otherwise-successful run: ``OSError`` (CSV write) and
    ``PipelexError`` (e.g. ``CostRegistryError``) are caught and logged as a warning.

    Args:
        pipeline_run_id: The run whose usage is being reported (titles the table, names nothing else).
        tokens_usages: The usage records assembled onto ``pipe_output.tokens_usages``.
        is_generate_costs: The resolved ``--costs`` gate for this run.
    """
    if not is_generate_costs or not tokens_usages:
        return
    if CostRegistry.compute_total_cost_of_usages(tokens_usages) <= 0:
        return

    reporting_config = get_config().pipelex.reporting_config
    print_to_console = reporting_config.is_log_costs_to_console
    is_csv_enabled = reporting_config.is_generate_cost_report_file_enabled
    if not (print_to_console or is_csv_enabled):
        return

    cost_report_file_path: Path | None = None
    if is_csv_enabled:
        ensure_path(Path(reporting_config.cost_report_dir_path))
        cost_report_file_path = get_incremental_file_path(
            base_path=Path(reporting_config.cost_report_dir_path),
            base_name=reporting_config.cost_report_base_name,
            extension=reporting_config.cost_report_extension,
        )

    try:
        CostRegistry.generate_report(
            pipeline_run_id=pipeline_run_id,
            tokens_usages=tokens_usages,
            unit_scale=reporting_config.cost_report_unit_scale,
            cost_report_file_path=cost_report_file_path,
            print_to_console=print_to_console,
        )
    except (OSError, PipelexError) as cost_report_error:
        log.warning(f"Cost report generation failed (run succeeded): {cost_report_error}")
