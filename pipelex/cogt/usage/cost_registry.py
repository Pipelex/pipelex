import csv
from typing import Any

from pydantic import Field, RootModel
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import log
from pipelex.cogt.exceptions import CostRegistryError
from pipelex.cogt.llm.llm_report import LLMTokenCostReport, LLMTokenCostReportField, LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.costs_per_token import model_cost_per_token
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

CostRegistryRoot = list[LLMTokenCostReport]


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
        llm_tokens_usages: list[LLMTokensUsage],
        unit_scale: float,
        cost_report_file_path: str | None = None,
    ):
        if not llm_tokens_usages:
            if pipeline_run_id != "untitled":
                log.warning(f"No report to generate for pipeline '{pipeline_run_id}'")
            else:
                log.verbose(f"No report to generate for pipeline '{pipeline_run_id}'")
            return
        cost_registry = CostRegistry()
        for llm_tokens_usage in llm_tokens_usages:
            cost_report = cls.complete_cost_report(llm_tokens_usage=llm_tokens_usage)
            cost_registry.root.append(cost_report)

        records = cost_registry.to_records()

        # Calculate total costs overall
        total_nb_tokens_input_cached = sum(record[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED] for record in records)
        total_nb_tokens_input_non_cached = sum(record[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED] for record in records)
        total_nb_tokens_input_joined = sum(record[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED] for record in records)
        total_nb_tokens_output = sum(record[LLMTokenCostReportField.NB_TOKENS_OUTPUT] for record in records)
        total_cost_input_cached = sum(record[LLMTokenCostReportField.COST_INPUT_CACHED] for record in records)
        total_cost_input_non_cached = sum(record[LLMTokenCostReportField.COST_INPUT_NON_CACHED] for record in records)
        total_cost_input_joined = sum(record[LLMTokenCostReportField.COST_INPUT_JOINED] for record in records)
        total_cost_output = sum(record[LLMTokenCostReportField.COST_OUTPUT] for record in records)
        total_cost = cls.compute_total_cost(
            input_non_cached_cost=total_cost_input_non_cached,
            input_cached_cost=total_cost_input_cached,
            output_cost=total_cost_output,
        )

        # Calculate costs per LLM model - group by LLM name
        grouped_by_llm: dict[str, dict[str, float]] = {}
        for record in records:
            llm_name = record[LLMTokenCostReportField.LLM_NAME]
            if llm_name not in grouped_by_llm:
                grouped_by_llm[llm_name] = {
                    LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 0,
                    LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED: 0,
                    LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED: 0,
                    LLMTokenCostReportField.NB_TOKENS_OUTPUT: 0,
                    LLMTokenCostReportField.COST_INPUT_CACHED: 0.0,
                    LLMTokenCostReportField.COST_INPUT_NON_CACHED: 0.0,
                    LLMTokenCostReportField.COST_INPUT_JOINED: 0.0,
                    LLMTokenCostReportField.COST_OUTPUT: 0.0,
                }

            # Aggregate values
            for field in [
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED,
                LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED,
                LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED,
                LLMTokenCostReportField.NB_TOKENS_OUTPUT,
                LLMTokenCostReportField.COST_INPUT_CACHED,
                LLMTokenCostReportField.COST_INPUT_NON_CACHED,
                LLMTokenCostReportField.COST_INPUT_JOINED,
                LLMTokenCostReportField.COST_OUTPUT,
            ]:
                grouped_by_llm[llm_name][field] += record[field]

        if not grouped_by_llm:
            msg = "Empty report aggregation by LLM name"
            raise CostRegistryError(msg)

        console = Console()
        title = "Costs by LLM model"
        title += f" for pipeline '{pipeline_run_id}'"
        table = Table(title=title, box=box.ROUNDED)

        scale_str: str
        if unit_scale == 1:
            scale_str = ""
        else:
            scale_str = str(unit_scale)
        # Add columns
        table.add_column("Model", style="cyan")
        table.add_column("Input Cached", justify="right", style="green")
        table.add_column("Input Non Cached", justify="right", style="green")
        table.add_column("Input Joined", justify="right", style="green")
        table.add_column("Output", justify="right", style="green")
        table.add_column(f"Input Cached Cost ({scale_str}$)", justify="right", style="yellow")
        table.add_column(f"Input Non Cached Cost ({scale_str}$)", justify="right", style="yellow")
        table.add_column(f"Input Joined Cost ({scale_str}$)", justify="right", style="yellow")
        table.add_column(f"Output Cost ({scale_str}$)", justify="right", style="yellow")
        table.add_column(f"Total Cost ({scale_str}$)", justify="right", style="bold yellow")

        # Add rows for each LLM model
        for llm_name, aggregated_data in grouped_by_llm.items():
            row_total_cost = cls.compute_total_cost(
                input_non_cached_cost=aggregated_data[LLMTokenCostReportField.COST_INPUT_NON_CACHED],
                input_cached_cost=aggregated_data[LLMTokenCostReportField.COST_INPUT_CACHED],
                output_cost=aggregated_data[LLMTokenCostReportField.COST_OUTPUT],
            )
            table.add_row(
                llm_name,
                f"{int(aggregated_data[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED]):,}",
                f"{int(aggregated_data[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED]):,}",
                f"{int(aggregated_data[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED]):,}",
                f"{int(aggregated_data[LLMTokenCostReportField.NB_TOKENS_OUTPUT]):,}",
                f"{aggregated_data[LLMTokenCostReportField.COST_INPUT_CACHED] / unit_scale:.4f}",
                f"{aggregated_data[LLMTokenCostReportField.COST_INPUT_NON_CACHED] / unit_scale:.4f}",
                f"{aggregated_data[LLMTokenCostReportField.COST_INPUT_JOINED] / unit_scale:.4f}",
                f"{aggregated_data[LLMTokenCostReportField.COST_OUTPUT] / unit_scale:.4f}",
                f"{row_total_cost / unit_scale:.4f}",
            )

        # add total row
        footer_style = "bold"
        table.add_row(
            "Total",
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

        if cost_report_file_path:
            cls.save_to_csv(records, cost_report_file_path)

    @staticmethod
    def save_to_csv(records: list[dict[str, Any]], file_path: str) -> None:
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
    def compute_total_cost(cls, input_non_cached_cost: float, input_cached_cost: float, output_cost: float) -> float:
        return input_non_cached_cost + input_cached_cost + output_cost

    @classmethod
    def compute_cost_report(cls, llm_tokens_usage: LLMTokensUsage) -> LLMTokenCostReport:
        costs_by_token_category: CostsByCategoryDict = {}
        for token_type, nb_tokens in llm_tokens_usage.nb_tokens_by_category.items():
            cost_per_token = model_cost_per_token(
                costs=llm_tokens_usage.unit_costs,
                cost_category=token_type.to_cost_category,
            )
            costs_by_token_category[token_type.to_cost_category] = cost_per_token * nb_tokens
        return LLMTokenCostReport(
            job_metadata=llm_tokens_usage.job_metadata,
            inference_model_name=llm_tokens_usage.inference_model_name,
            platform_llm_id=llm_tokens_usage.inference_model_id,
            nb_tokens_by_category=llm_tokens_usage.nb_tokens_by_category,
            costs_by_token_category=costs_by_token_category,
        )

    @classmethod
    def complete_cost_report(cls, llm_tokens_usage: LLMTokensUsage) -> LLMTokenCostReport:
        cost_report = cls.compute_cost_report(llm_tokens_usage=llm_tokens_usage)
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
            costs=llm_tokens_usage.unit_costs,
            cost_category=CostCategory.INPUT_NON_CACHED,
        )
        costs_input_cached = cost_report.costs_by_token_category.get(CostCategory.INPUT_CACHED, 0)
        cost_report.costs_by_token_category[CostCategory.INPUT_CACHED] = costs_input_cached
        cost_report.costs_by_token_category[CostCategory.INPUT_JOINED] = (
            costs_input_cached + cost_report.costs_by_token_category[CostCategory.INPUT_NON_CACHED]
        )
        return cost_report
