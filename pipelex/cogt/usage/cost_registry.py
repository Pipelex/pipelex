import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import Field, RootModel
from rich import box
from rich.table import Table

from pipelex import log
from pipelex.cogt.exceptions import CostRegistryError
from pipelex.cogt.extract.extract_report import ExtractTokenCostReport, ExtractTokenCostReportField, ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokenCostReport, ImgGenTokenCostReportField, ImgGenTokensUsage
from pipelex.cogt.llm.llm_report import LLMTokenCostReport, LLMTokenCostReportField, LLMTokensUsage
from pipelex.cogt.search.search_report import SearchTokenCostReport, SearchTokenCostReportField, SearchTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.costs_per_token import model_cost_per_token
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.runtime_hub import get_console
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

TokensUsage = LLMTokensUsage | ImgGenTokensUsage | ExtractTokensUsage | SearchTokensUsage
TokenCostReport = LLMTokenCostReport | ImgGenTokenCostReport | ExtractTokenCostReport | SearchTokenCostReport
CostRegistryRoot = list[TokenCostReport]


def compute_tokens_usage_cost(tokens_usage: TokensUsage) -> float | None:
    """Compute the canonical USD cost of a single inference call, or None when unrated.

    Returns ``None`` when the usage carries no rate table (``unit_costs`` is empty:
    own-GPU models, dry/mock runs). Otherwise returns the same canonical total the cost
    table reports for the call — input_non_cached + input_cached + output component
    costs, with the cached-discount fallback from ``model_cost_per_token``. Categories
    the cost engine excludes from totals (audio, reasoning, prediction) are excluded
    here too: one cost engine, one total.
    """
    if not tokens_usage.unit_costs:
        return None
    nb_tokens_input_joined = tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0)
    nb_tokens_input_cached = tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT_CACHED, 0)
    nb_tokens_input_non_cached = nb_tokens_input_joined - nb_tokens_input_cached
    nb_tokens_output = tokens_usage.nb_tokens_by_category.get(TokenCategory.OUTPUT, 0)
    input_non_cached_cost = nb_tokens_input_non_cached * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.INPUT_NON_CACHED,
    )
    input_cached_cost = nb_tokens_input_cached * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.INPUT_CACHED,
    )
    output_cost = nb_tokens_output * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.OUTPUT,
    )
    return CostRegistry.compute_total_cost(
        input_non_cached_cost=input_non_cached_cost,
        input_cached_cost=input_cached_cost,
        output_cost=output_cost,
    )


class AggregatedCosts(NamedTuple):
    """One run's token usage aggregated for reporting: flat records, per-model groups, and run totals.

    ``total_cost`` is the real/unscaled USD total; ``total_nb_tokens`` is input-joined + output across all
    usages. Computing both here, once, makes this the single source of truth the table footer, the agent JSON
    summary, and the dry-run suppression gate all read from — so they can never disagree.
    """

    records: list[dict[str, Any]]
    grouped_by_model: dict[str, dict[str, float]]
    model_types: dict[str, str]
    total_cost: float
    total_nb_tokens: int

    @property
    def has_reportable_usage(self) -> bool:
        """True when the run did real work worth reporting: any tokens OR any cost.

        Dry runs emit zero-token, zero-cost synthetic usage, so this is False for them (the cost report is
        suppressed). A real run on a free/zero-price model has tokens (cost 0), so this stays True and its
        token usage is still reported — gating on cost alone would wrongly hide it.
        """
        return self.total_nb_tokens > 0 or self.total_cost > 0


class CostRegistry(RootModel[CostRegistryRoot]):
    root: CostRegistryRoot = Field(default_factory=empty_list_factory_of(LLMTokenCostReport))

    def to_records(self) -> list[dict[str, Any]]:
        """Convert cost reports to list of flat dictionaries."""
        records: list[dict[str, Any]] = []
        for token_cost_report in self.root:
            record_dict = token_cost_report.as_flat_dictionary()
            records.append(record_dict)
        return records

    @classmethod
    def generate_report(
        cls,
        pipeline_run_id: str,
        *,
        tokens_usages: Sequence[TokensUsage],
        unit_scale: float,
        cost_report_file_path: Path | None = None,
        print_to_console: bool = True,
    ):
        if not tokens_usages:
            if pipeline_run_id != "untitled":
                log.warning(f"No report to generate for pipeline '{pipeline_run_id}'")
            else:
                log.verbose(f"No report to generate for pipeline '{pipeline_run_id}'")
            return
        cls.render_report(
            cls.aggregate_costs(tokens_usages=tokens_usages),
            pipeline_run_id=pipeline_run_id,
            unit_scale=unit_scale,
            cost_report_file_path=cost_report_file_path,
            print_to_console=print_to_console,
        )

    @classmethod
    def render_report(
        cls,
        aggregated: AggregatedCosts,
        *,
        pipeline_run_id: str,
        unit_scale: float,
        cost_report_file_path: Path | None = None,
        print_to_console: bool = True,
    ) -> None:
        """Render a pre-aggregated cost report to the console (Rich table) and/or a CSV file.

        Split out of ``generate_report`` so a caller that already aggregated — the CLI renderer, which needs
        the totals to decide whether to report at all — renders from a single aggregation pass instead of
        aggregating a second time just to display.
        """
        records = aggregated.records
        grouped_by_model = aggregated.grouped_by_model
        model_types = aggregated.model_types

        # Use LLMTokenCostReportField for field names (same string values as ImgGenTokenCostReportField)
        report_field = LLMTokenCostReportField

        # Per-category footer subtotals (display detail). The headline total comes from the single aggregation
        # (aggregated.total_cost) so the footer, the agent JSON, and the suppression gate share one definition.
        total_nb_tokens_input_cached = sum(record.get(report_field.NB_TOKENS_INPUT_CACHED, 0) for record in records)
        total_nb_tokens_input_non_cached = sum(record.get(report_field.NB_TOKENS_INPUT_NON_CACHED, 0) for record in records)
        total_nb_tokens_input_joined = sum(record.get(report_field.NB_TOKENS_INPUT_JOINED, 0) for record in records)
        total_nb_tokens_output = sum(record.get(report_field.NB_TOKENS_OUTPUT, 0) for record in records)
        total_cost_input_cached = sum(record.get(report_field.COST_INPUT_CACHED, 0) for record in records)
        total_cost_input_non_cached = sum(record.get(report_field.COST_INPUT_NON_CACHED, 0) for record in records)
        total_cost_input_joined = sum(record.get(report_field.COST_INPUT_JOINED, 0) for record in records)
        total_cost_output = sum(record.get(report_field.COST_OUTPUT, 0) for record in records)
        total_cost = aggregated.total_cost

        if not grouped_by_model:
            msg = "Empty report aggregation by model name"
            raise CostRegistryError(msg)

        if print_to_console:
            console = get_console()
            title = f"Costs by model for pipeline '{pipeline_run_id}'"
            table = Table(title=title, box=box.ROUNDED)

            scale_str: str
            if unit_scale == 1:
                scale_str = ""
            else:
                scale_str = str(unit_scale)
            # Add columns
            table.add_column("Model", style="cyan", overflow="fold", width=30)
            table.add_column("Type", style="dim cyan", width=8)
            table.add_column("Input Cached", justify="right", style="green")
            table.add_column("Input Non Cached", justify="right", style="green")
            table.add_column("Input Joined", justify="right", style="green")
            table.add_column("Output", justify="right", style="green")
            table.add_column(f"Input Cached Cost ({scale_str}$)", justify="right", style="yellow")
            table.add_column(f"Input Non Cached Cost ({scale_str}$)", justify="right", style="yellow")
            table.add_column(f"Input Joined Cost ({scale_str}$)", justify="right", style="yellow")
            table.add_column(f"Output Cost ({scale_str}$)", justify="right", style="yellow")
            table.add_column(f"Total Cost ({scale_str}$)", justify="right", style="bold yellow")

            # Add rows for each model
            for model_name, aggregated_data in grouped_by_model.items():
                row_total_cost = cls.compute_total_cost(
                    input_non_cached_cost=aggregated_data[report_field.COST_INPUT_NON_CACHED],
                    input_cached_cost=aggregated_data[report_field.COST_INPUT_CACHED],
                    output_cost=aggregated_data[report_field.COST_OUTPUT],
                )
                table.add_row(
                    model_name,
                    model_types.get(model_name, "llm"),
                    f"{int(aggregated_data[report_field.NB_TOKENS_INPUT_CACHED]):,}",
                    f"{int(aggregated_data[report_field.NB_TOKENS_INPUT_NON_CACHED]):,}",
                    f"{int(aggregated_data[report_field.NB_TOKENS_INPUT_JOINED]):,}",
                    f"{int(aggregated_data[report_field.NB_TOKENS_OUTPUT]):,}",
                    f"{aggregated_data[report_field.COST_INPUT_CACHED] / unit_scale:.4f}",
                    f"{aggregated_data[report_field.COST_INPUT_NON_CACHED] / unit_scale:.4f}",
                    f"{aggregated_data[report_field.COST_INPUT_JOINED] / unit_scale:.4f}",
                    f"{aggregated_data[report_field.COST_OUTPUT] / unit_scale:.4f}",
                    f"{row_total_cost / unit_scale:.4f}",
                )

            # add total row
            footer_style = "bold"
            table.add_row(
                "Total",
                "",
                f"{total_nb_tokens_input_cached:,}",
                f"{total_nb_tokens_input_non_cached:,}",
                f"{total_nb_tokens_input_joined:,}",
                f"{total_nb_tokens_output:,}",
                f"{total_cost_input_cached / unit_scale:.4f}",
                f"{total_cost_input_non_cached / unit_scale:.4f}",
                f"{total_cost_input_joined / unit_scale:.4f}",
                f"{total_cost_output / unit_scale:.4f}",
                f"{total_cost / unit_scale:.4f}",
                style=footer_style,
                end_section=True,
            )

            console.print(table)
            console.print(" [dim]Note: some costs might be missing or not up-to-date.[/dim]")

        if cost_report_file_path:
            cls.save_to_csv(records, file_path=cost_report_file_path)

    @staticmethod
    def save_to_csv(records: list[dict[str, Any]], *, file_path: Path) -> None:
        """Save records to CSV file."""
        if not records:
            return

        # Collect all unique field names across all records
        all_fieldnames: set[str] = set()
        for record in records:
            all_fieldnames.update(record.keys())

        # Sort fieldnames for consistent column order
        fieldnames = sorted(all_fieldnames)

        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    @classmethod
    def compute_total_cost(cls, *, input_non_cached_cost: float, input_cached_cost: float, output_cost: float) -> float:
        return input_non_cached_cost + input_cached_cost + output_cost

    @classmethod
    def aggregate_costs(cls, tokens_usages: Sequence[TokensUsage]) -> AggregatedCosts:
        """Aggregate token usages into flat records, per-model groups, and run totals — in one pass.

        The single source of truth for a run's reporting data. Shared by ``render_report`` (Rich table / CSV)
        and ``build_cost_summary`` (agent CLI JSON), and consulted by the CLI renderer's suppression gate via
        :attr:`AggregatedCosts.has_reportable_usage` — so the table, the JSON, and the gate never disagree on
        what a run cost or whether it is worth reporting.
        """
        cost_registry = cls()
        for tokens_usage in tokens_usages:
            cost_registry.root.append(cls.complete_cost_report(tokens_usage=tokens_usage))
        records = cost_registry.to_records()

        report_field = LLMTokenCostReportField
        grouped_by_model: dict[str, dict[str, float]] = {}
        model_types: dict[str, str] = {}
        for record in records:
            model_name = (
                record.get(report_field.LLM_NAME)
                or record.get(ImgGenTokenCostReportField.IMG_GEN_NAME)
                or record.get(ExtractTokenCostReportField.EXTRACT_NAME)
                or record.get(SearchTokenCostReportField.SEARCH_NAME, "unknown")
            )
            model_types[model_name] = record.get(report_field.MODEL_TYPE, "llm")
            if model_name not in grouped_by_model:
                grouped_by_model[model_name] = {
                    report_field.NB_TOKENS_INPUT_CACHED: 0,
                    report_field.NB_TOKENS_INPUT_NON_CACHED: 0,
                    report_field.NB_TOKENS_INPUT_JOINED: 0,
                    report_field.NB_TOKENS_OUTPUT: 0,
                    report_field.COST_INPUT_CACHED: 0.0,
                    report_field.COST_INPUT_NON_CACHED: 0.0,
                    report_field.COST_INPUT_JOINED: 0.0,
                    report_field.COST_OUTPUT: 0.0,
                }
            for field in [
                report_field.NB_TOKENS_INPUT_CACHED,
                report_field.NB_TOKENS_INPUT_NON_CACHED,
                report_field.NB_TOKENS_INPUT_JOINED,
                report_field.NB_TOKENS_OUTPUT,
                report_field.COST_INPUT_CACHED,
                report_field.COST_INPUT_NON_CACHED,
                report_field.COST_INPUT_JOINED,
                report_field.COST_OUTPUT,
            ]:
                grouped_by_model[model_name][field] += record.get(field, 0)

        total_cost = cls.compute_total_cost(
            input_non_cached_cost=sum(record.get(report_field.COST_INPUT_NON_CACHED, 0) for record in records),
            input_cached_cost=sum(record.get(report_field.COST_INPUT_CACHED, 0) for record in records),
            output_cost=sum(record.get(report_field.COST_OUTPUT, 0) for record in records),
        )
        total_nb_tokens = int(
            sum(record.get(report_field.NB_TOKENS_INPUT_JOINED, 0) for record in records)
            + sum(record.get(report_field.NB_TOKENS_OUTPUT, 0) for record in records)
        )
        return AggregatedCosts(
            records=records,
            grouped_by_model=grouped_by_model,
            model_types=model_types,
            total_cost=total_cost,
            total_nb_tokens=total_nb_tokens,
        )

    @classmethod
    def build_cost_summary(cls, tokens_usages: Sequence[TokensUsage]) -> dict[str, Any] | None:
        """Build a JSON-serializable cost summary (real/unscaled USD) for machine consumers.

        Returns ``None`` only when the run did no reportable work (a dry run: zero tokens and zero cost), so a
        real run on a free/zero-price model still reports its token usage with ``total_cost`` 0. Otherwise
        returns ``{"total_cost": float, "by_model": [{model, model_type, nb_tokens_input, nb_tokens_output, cost}, ...]}``.
        """
        aggregated = cls.aggregate_costs(tokens_usages=tokens_usages)
        if not aggregated.has_reportable_usage:
            return None

        report_field = LLMTokenCostReportField
        by_model: list[dict[str, Any]] = []
        for model_name, aggregated_data in aggregated.grouped_by_model.items():
            model_cost = cls.compute_total_cost(
                input_non_cached_cost=aggregated_data[report_field.COST_INPUT_NON_CACHED],
                input_cached_cost=aggregated_data[report_field.COST_INPUT_CACHED],
                output_cost=aggregated_data[report_field.COST_OUTPUT],
            )
            by_model.append(
                {
                    "model": model_name,
                    "model_type": aggregated.model_types.get(model_name, "llm"),
                    "nb_tokens_input": int(aggregated_data[report_field.NB_TOKENS_INPUT_JOINED]),
                    "nb_tokens_output": int(aggregated_data[report_field.NB_TOKENS_OUTPUT]),
                    "cost": model_cost,
                }
            )
        return {"total_cost": aggregated.total_cost, "by_model": by_model}

    @classmethod
    def compute_cost_report(cls, tokens_usage: TokensUsage) -> TokenCostReport:
        costs_by_token_category: CostsByCategoryDict = {}
        for token_type, nb_tokens in tokens_usage.nb_tokens_by_category.items():
            cost_per_token = model_cost_per_token(
                costs=tokens_usage.unit_costs,
                cost_category=token_type.to_cost_category,
            )
            costs_by_token_category[token_type.to_cost_category] = cost_per_token * nb_tokens

        if isinstance(tokens_usage, LLMTokensUsage):
            return LLMTokenCostReport(
                model_type=tokens_usage.model_type,
                job_metadata=tokens_usage.job_metadata,
                inference_model_name=tokens_usage.inference_model_name,
                platform_model_id=tokens_usage.inference_model_id,
                nb_tokens_by_category=tokens_usage.nb_tokens_by_category,
                costs_by_token_category=costs_by_token_category,
            )
        if isinstance(tokens_usage, ImgGenTokensUsage):
            return ImgGenTokenCostReport(
                model_type=tokens_usage.model_type,
                job_metadata=tokens_usage.job_metadata,
                inference_model_name=tokens_usage.inference_model_name,
                platform_model_id=tokens_usage.inference_model_id,
                nb_tokens_by_category=tokens_usage.nb_tokens_by_category,
                costs_by_token_category=costs_by_token_category,
            )
        if isinstance(tokens_usage, SearchTokensUsage):
            return SearchTokenCostReport(
                model_type=tokens_usage.model_type,
                job_metadata=tokens_usage.job_metadata,
                inference_model_name=tokens_usage.inference_model_name,
                platform_model_id=tokens_usage.inference_model_id,
                nb_tokens_by_category=tokens_usage.nb_tokens_by_category,
                costs_by_token_category=costs_by_token_category,
            )
        return ExtractTokenCostReport(
            model_type=tokens_usage.model_type,
            job_metadata=tokens_usage.job_metadata,
            inference_model_name=tokens_usage.inference_model_name,
            platform_model_id=tokens_usage.inference_model_id,
            nb_tokens_by_category=tokens_usage.nb_tokens_by_category,
            costs_by_token_category=costs_by_token_category,
        )

    @classmethod
    def complete_cost_report(cls, tokens_usage: TokensUsage) -> TokenCostReport:
        cost_report = cls.compute_cost_report(tokens_usage=tokens_usage)
        # compute the input_non_cached tokens
        if cost_report.nb_tokens_by_category.get(TokenCategory.INPUT_NON_CACHED) is not None:
            msg = "CostCategory.INPUT_NON_CACHED already exists in the cost report"
            raise CostRegistryError(msg)
        # we use pop to remove input tokens which will be replaced by "input joined"
        nb_tokens_input_joined = cost_report.nb_tokens_by_category.pop(TokenCategory.INPUT, 0)
        cost_report.costs_by_token_category.pop(CostCategory.INPUT, None)

        nb_tokens_input_cached = cost_report.nb_tokens_by_category.get(TokenCategory.INPUT_CACHED, 0)
        nb_tokens_input_non_cached = nb_tokens_input_joined - nb_tokens_input_cached
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_JOINED] = nb_tokens_input_joined
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_NON_CACHED] = nb_tokens_input_non_cached
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_CACHED] = nb_tokens_input_cached

        cost_report.costs_by_token_category[CostCategory.INPUT_NON_CACHED] = nb_tokens_input_non_cached * model_cost_per_token(
            costs=tokens_usage.unit_costs,
            cost_category=CostCategory.INPUT_NON_CACHED,
        )
        costs_input_cached = cost_report.costs_by_token_category.get(CostCategory.INPUT_CACHED, 0)
        cost_report.costs_by_token_category[CostCategory.INPUT_CACHED] = costs_input_cached
        cost_report.costs_by_token_category[CostCategory.INPUT_JOINED] = (
            costs_input_cached + cost_report.costs_by_token_category[CostCategory.INPUT_NON_CACHED]
        )
        return cost_report
