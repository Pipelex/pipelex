# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import Field, RootModel
from rich import box
from rich.console import Console
from rich.table import Table
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import InferenceReportManagerError
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_report import LLMTokenCostReport, LLMTokenCostReportField, LLMTokensUsage, model_cost_per_token
from pipelex.cogt.llm.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.tools.utils.path_utils import ensure_path, get_incremental_file_path

LLMUsageRegistryRoot = List[LLMTokensUsage]
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

    @property
    def is_empty(self) -> bool:
        return not self.root


class UsageRegistry(RootModel[LLMUsageRegistryRoot]):
    root: LLMUsageRegistryRoot = Field(default_factory=list)


class InferenceReportManager(InferenceReportDelegate):
    def __init__(self):
        self.usage_registery = UsageRegistry()

    def reset(self):
        self.usage_registery = UsageRegistry()

    @property
    def report_config(self):
        return get_config().cogt.cogt_report_config

    # according to openai docs, cached input tokens are discounted 50%
    def _compute_total_cost(self, input_non_cached_cost: float, input_cached_cost: float, output_cost: float) -> float:
        return input_non_cached_cost + input_cached_cost + output_cost

    def _complete_cost_report(self, llm_tokens_usage: LLMTokensUsage) -> LLMTokenCostReport:
        cost_report = llm_tokens_usage.compute_cost_report()
        if not cost_report.job_metadata.project_id:
            cost_report.job_metadata.project_id = get_config().project_name
        # compute the input_non_cached tokens
        if cost_report.nb_tokens_by_category.get(TokenCategory.INPUT_NON_CACHED) is not None:
            raise InferenceReportManagerError("TokenCategory.INPUT_NON_CACHED already exists in the cost report")
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

    def _make_cost_registery(self) -> CostRegistry:
        cost_registery = CostRegistry()
        for llm_tokens_usage in self.usage_registery.root:
            cost_report = self._complete_cost_report(llm_tokens_usage=llm_tokens_usage)
            cost_registery.root.append(cost_report)
        return cost_registery

    @override
    def general_report(self):
        cost_registery = self._make_cost_registery()
        if cost_registery.is_empty:
            log.warning("Cost registry is empty")
            return

        cost_registery_df = cost_registery.to_dataframe()

        # Calculate total costs overall
        total_nb_tokens_input_cached = cost_registery_df[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_input_non_cached = cost_registery_df[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_input_joined = cost_registery_df[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_nb_tokens_output = cost_registery_df[LLMTokenCostReportField.NB_TOKENS_OUTPUT].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_cached = cost_registery_df[LLMTokenCostReportField.COST_INPUT_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_non_cached = cost_registery_df[LLMTokenCostReportField.COST_INPUT_NON_CACHED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_input_joined = cost_registery_df[LLMTokenCostReportField.COST_INPUT_JOINED].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost_output = cost_registery_df[LLMTokenCostReportField.COST_OUTPUT].sum()  # pyright: ignore[reportUnknownMemberType]
        total_cost = self._compute_total_cost(
            input_non_cached_cost=total_cost_input_non_cached,
            input_cached_cost=total_cost_input_cached,
            output_cost=total_cost_output,
        )

        # Calculate costs per LLM model
        llm_group = cost_registery_df.groupby(LLMTokenCostReportField.LLM_NAME)  # pyright: ignore[reportUnknownMemberType]
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
            raise InferenceReportManagerError("Empty report aggregation by LLM name")

        console = Console()
        table = Table(title="Costs by LLM model", box=box.ROUNDED)

        scale = self.report_config.cost_report_unit_scale
        scale_str: str
        if scale == 1:
            scale_str = ""
        else:
            scale_str = str(scale)
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
            row_total_cost = self._compute_total_cost(
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
                f"{row[LLMTokenCostReportField.COST_INPUT_CACHED] / scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_INPUT_NON_CACHED] / scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_INPUT_JOINED] / scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row[LLMTokenCostReportField.COST_OUTPUT] / scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
                f"{row_total_cost / scale:.4f}",  # pyright: ignore[reportUnknownVariableType]
            )

        # add total row
        footer_style = "bold"
        table.add_row(
            "Total",
            f"{total_nb_tokens_input_cached:,}",
            f"{total_nb_tokens_input_non_cached:,}",
            f"{total_nb_tokens_input_joined:,}",
            f"{total_nb_tokens_output:,}",
            f"{total_cost_input_cached / scale:.4f}",
            f"{total_cost_input_non_cached / scale:.4f}",
            f"{total_cost_input_joined / scale:.4f}",
            f"{total_cost_output / scale:.4f}",
            f"{total_cost / scale:.4f}",
            style=footer_style,
            end_section=True,
        )

        console.print(table)

        if self.report_config.is_generate_cost_report_file_enabled:
            ensure_path(self.report_config.cost_report_dir_path)
            cost_report_file_path = get_incremental_file_path(
                base_path=self.report_config.cost_report_dir_path,
                base_name=self.report_config.cost_report_base_name,
                extension=self.report_config.cost_report_extension,
            )
            cost_registery_df.to_excel(  # pyright: ignore[reportUnknownMemberType]
                cost_report_file_path,
                index=False,
            )

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract):
        log.info(f"Inference job '{inference_job.job_metadata.unit_job_id}' completed in {inference_job.job_metadata.duration:.2f} seconds")
        if isinstance(inference_job, LLMJob):
            llm_job: LLMJob = inference_job
            self._report_llm_job(llm_job=llm_job)

    def _report_llm_job(self, llm_job: LLMJob):
        llm_tokens_usage = llm_job.job_report.llm_tokens_usage

        if not llm_tokens_usage:
            log.warning("LLM job has no llm_tokens_usage")
            return

        llm_token_cost_report: Optional[LLMTokenCostReport] = None

        if self.report_config.is_log_costs_to_console:
            llm_token_cost_report = self._complete_cost_report(llm_tokens_usage=llm_tokens_usage)

        self.usage_registery.root.append(llm_tokens_usage)

        if self.report_config.is_log_costs_to_console:
            log.verbose(llm_token_cost_report, title="Token Cost report")
