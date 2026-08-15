"""Render the end-of-run cost report from usage assembled on the pipeline output.

The cost report is sourced from the ``tokens_usages`` list that rides back on ``PipeOutput``
(assembled from the trace-event stream at the end of the run), not from a live per-process
registry. The **main** CLI (``pipelex run``) calls this to render the console table / CSV; the
**agent** CLI does not — it builds a machine-readable ``cost_report`` object via
``CostRegistry.build_cost_summary`` for its JSON envelope instead (no Rich table on its surface).
"""

from collections.abc import Sequence
from pathlib import Path

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
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
    (``tokens_usages`` is a non-empty list), AND the run did real work
    (:attr:`~pipelex.cogt.usage.cost_registry.AggregatedCosts.has_reportable_usage` — any tokens or any cost).
    The work guard suppresses dry runs (which emit zero-token, zero-cost synthetic usage) while still
    reporting real runs on free/zero-price models, whose tokens matter even though they cost nothing —
    gating on cost alone would wrongly hide them. The two channels follow D6, each applied only when costs
    are on:

    - console (Rich table): gated by ``reporting_config.is_log_costs_to_console``
    - CSV file: gated by ``reporting_config.is_generate_cost_report_file_enabled``

    A cost-report failure never fails an otherwise-successful run: the aggregation, the CSV directory/path
    setup, and the render all run inside one try, so ``OSError`` (directory create / CSV write),
    ``UnicodeEncodeError`` (a record string the CSV's UTF-8 encoder can't represent, e.g. a lone surrogate),
    and ``PipelexError`` (e.g. ``CostRegistryError``) are caught and logged as a warning rather than propagating.

    Args:
        pipeline_run_id: The run whose usage is being reported (titles the table, names nothing else).
        tokens_usages: The usage records assembled onto ``pipe_output.tokens_usages``.
        is_generate_costs: The resolved ``--costs`` gate for this run.
    """
    if not is_generate_costs or not tokens_usages:
        return

    reporting_config = get_config().runtime.reporting
    print_to_console = reporting_config.is_log_costs_to_console
    is_csv_enabled = reporting_config.is_generate_cost_report_file_enabled
    if not (print_to_console or is_csv_enabled):
        return

    try:
        # One aggregation pass feeds both the suppression decision and the render (no double aggregation).
        aggregated = CostRegistry.aggregate_costs(tokens_usages)
        if not aggregated.has_reportable_usage:
            return

        cost_report_file_path: Path | None = None
        if is_csv_enabled:
            ensure_path(Path(reporting_config.cost_report_dir_path))
            cost_report_file_path = get_incremental_file_path(
                base_path=Path(reporting_config.cost_report_dir_path),
                base_name=reporting_config.cost_report_base_name,
                extension=reporting_config.cost_report_extension,
            )

        CostRegistry.render_report(
            aggregated,
            pipeline_run_id=pipeline_run_id,
            unit_scale=reporting_config.cost_report_unit_scale,
            cost_report_file_path=cost_report_file_path,
            print_to_console=print_to_console,
        )
    except (OSError, UnicodeEncodeError, PipelexError) as cost_report_error:
        log.warning(f"Cost report generation failed (run succeeded): {cost_report_error}")


def render_cost_report_for_output(pipe_output: PipeOutput) -> None:
    """Render the end-of-run cost report from a finished output (self-contained, one-arg submitter helper).

    The standard submitter convenience over :func:`render_run_cost_report`: a finished
    :class:`~pipelex.core.pipes.pipe_output.PipeOutput` already carries the three values the primitive
    needs, so callers (the ``pipelex run`` CLI, external embedders) no longer re-derive them by hand.

    Crucially, the ``--costs`` gate is read **off the output, not config**:
    :attr:`~pipelex.core.pipes.pipe_output.PipeOutput.tokens_usages` is ``None`` exactly when cost
    reporting was off for this run. The runner already resolved that decision at run time (with all
    ``--costs/--no-costs`` overrides applied) and recorded it on the output. Re-reading global config to
    reconstruct it would only be correct when config wasn't overridden or mutated between run and render —
    the output is authoritative, config is not.

    Outcome-identical to the historical CLI gate (``execution_config.is_generate_usage``): the primitive
    ANDs both guards (``not is_generate_costs or not tokens_usages``), so the cases where the two sources
    disagree (usage on but tracing off → ``tokens_usages is None``) no-op either way.

    Args:
        pipe_output: The finished run output carrying ``pipeline_run_id`` and ``tokens_usages``.
    """
    render_run_cost_report(
        pipeline_run_id=pipe_output.pipeline_run_id,
        tokens_usages=pipe_output.tokens_usages,
        is_generate_costs=pipe_output.tokens_usages is not None,
    )
