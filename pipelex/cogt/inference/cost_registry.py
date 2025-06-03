from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import Field, RootModel
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import log
from pipelex.cogt.exceptions import CostRegistryError
from pipelex.cogt.llm.llm_report import LLMTokenCostReport, LLMTokenCostReportField, LLMTokensUsage, model_cost_per_token
from pipelex.cogt.llm.token_category import TokenCategory

CostRegistryRoot = List[LLMTokenCostReport]


class CostRegistry(RootModel[CostRegistryRoot]):
    root: CostRegistryRoot = Field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        records: List[Dict[str, Any]] = []
        for token_cost_report in self.root:
            record_dict = token_cost_report.as_flat_dictionary()
            records.append(record_dict)
        df = pd.DataFrame(records)
        return df

    @classmethod
    def generate_report(
        cls,
        pipeline_run_id: str,
        llm_tokens_usages: List[LLMTokensUsage],
        unit_scale: float,
        cost_report_file_path: Optional[str] = None,
    ):
        if not llm_tokens_usages:
            log.warning(f"No report to generate for pipeline '{pipeline_run_id}'")
            return
        cost_registry = CostRegistry()
        for llm_tokens_usage in llm_tokens_usages:
            cost_report = cls.complete_cost_report(llm_tokens_usage=llm_tokens_usage)
            cost_registry.root.append(cost_report)

        cost_registry_df = cost_registry.to_dataframe()

        # Calculate total costs overall
        total_nb_tokens_input_cached = cost_registry_df[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_input_non_cached = cost_registry_df[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_input_joined = cost_registry_df[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_output = cost_registry_df[LLMTokenCostReportField.NB_TOKENS_OUTPUT].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_cached = cost_registry_df[LLMTokenCostReportField.COST_INPUT_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_non_cached = cost_registry_df[LLMTokenCostReportField.COST_INPUT_NON_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_joined = cost_registry_df[LLMTokenCostReportField.COST_INPUT_JOINED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_output = cost_registry_df[LLMTokenCostReportField.COST_OUTPUT].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost = cls.compute_total_cost(
            input_non_cached_cost=total_cost_input_non_cached,
            input_cached_cost=total_cost_input_cached,
            output_cost=total_cost_output,
        )

        # Calculate costs per LLM model
        llm_group = cost_registry_df.groupby(LLMTokenCostReportField.LLM_NAME)  # pyright: ignore[reportUnknownMemberType]
        agg_by_llm_name = llm_group.agg(  # pyright: ignore[reportUnknownMemberType]
            {
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: "sum",
                LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED: "sum",
                LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED: "sum",
                LLMTokenCostReportField.NB_TOKENS_OUTPUT: "sum",
                LLMTokenCostReportField.COST_INPUT_CACHED: "sum",
                LLMTokenCostReportField.COST_INPUT_NON_CACHED: "sum",
                LLMTokenCostReportField.COST_INPUT_JOINED: "sum",
                LLMTokenCostReportField.COST_OUTPUT: "sum",
            }
        ).reset_index()
        if agg_by_llm_name is None or agg_by_llm_name.empty:  # pyright: ignore[reportUnnecessaryComparison]
            raise CostRegistryError("Empty report aggregation by LLM name")

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

        for _, row in agg_by_llm_name.iterrows():  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            llm_name = row[LLMTokenCostReportField.LLM_NAME]  # pyright: ignore[reportUnknownVariableType]
            row_total_cost = cls.compute_total_cost(
                input_non_cached_cost=row[LLMTokenCostReportField.COST_INPUT_NON_CACHED],  # pyright: ignore[reportUnknownArgumentType]
                input_cached_cost=row[LLMTokenCostReportField.COST_INPUT_CACHED],  # pyright: ignore[reportUnknownArgumentType]
                output_cost=row[LLMTokenCostReportField.COST_OUTPUT],  # pyright: ignore[reportUnknownArgumentType]
            )
            table.add_row(
                llm_name,  # pyright: ignore[reportUnknownArgumentType]
                f"{row[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED]:,}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED]:,}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED]:,}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.NB_TOKENS_OUTPUT]:,}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_INPUT_CACHED] / unit_scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_INPUT_NON_CACHED] / unit_scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_INPUT_JOINED] / unit_scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_OUTPUT] / unit_scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row_total_cost / unit_scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
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
            cost_registry_df.to_excel(  # pyright: ignore[reportUnknownMemberType]
                cost_report_file_path,
                index=False,
            )

    @classmethod
    def compute_total_cost(cls, input_non_cached_cost: float, input_cached_cost: float, output_cost: float) -> float:
        return input_non_cached_cost + input_cached_cost + output_cost

    @classmethod
    def complete_cost_report(cls, llm_tokens_usage: LLMTokensUsage) -> LLMTokenCostReport:
        cost_report = llm_tokens_usage.compute_cost_report()
        # compute the input_non_cached tokens
        if cost_report.nb_tokens_by_category.get(TokenCategory.INPUT_NON_CACHED) is not None:
            raise CostRegistryError("TokenCategory.INPUT_NON_CACHED already exists in the cost report")
        # we use pop to remove input tokens which will be replaced by "input joined"
        nb_tokens_input_joined = cost_report.nb_tokens_by_category.pop(TokenCategory.INPUT, 0)
        cost_report.costs_by_token_category.pop(TokenCategory.INPUT, None)

        nb_tokens_input_cached = cost_report.nb_tokens_by_category.get(TokenCategory.INPUT_CACHED, 0)
        nb_tokens_input_non_cached = nb_tokens_input_joined - nb_tokens_input_cached
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_JOINED] = nb_tokens_input_joined
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_NON_CACHED] = nb_tokens_input_non_cached
        cost_report.nb_tokens_by_category[TokenCategory.INPUT_CACHED] = nb_tokens_input_cached

        cost_report.costs_by_token_category[TokenCategory.INPUT_NON_CACHED] = nb_tokens_input_non_cached * model_cost_per_token(
            llm_engine=llm_tokens_usage.llm_engine, token_type=TokenCategory.INPUT_NON_CACHED
        )
        costs_input_cached = cost_report.costs_by_token_category.get(TokenCategory.INPUT_CACHED, 0)
        cost_report.costs_by_token_category[TokenCategory.INPUT_CACHED] = costs_input_cached
        cost_report.costs_by_token_category[TokenCategory.INPUT_JOINED] = (
            costs_input_cached + cost_report.costs_by_token_category[TokenCategory.INPUT_NON_CACHED]
        )
        return cost_report
