"""Unit tests for the Phase-3 end-of-run cost-report renderer.

``render_run_cost_report`` is the single event-sourced renderer both CLIs call: it reads the
usage assembled onto ``pipe_output.tokens_usages`` and renders it through the two D6 channels
(console + CSV), each gated by the reporting config and the resolved ``--costs`` switch.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import CostRegistryError
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.reporting.cost_report_renderer import render_run_cost_report
from pipelex.system.job_metadata import JobMetadata

_RUN_ID = "test-run"


def _usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
    )


def _zero_cost_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    """A dry-run-shaped usage: no tokens -> zero tokens and zero cost."""
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="dry-model",
        inference_model_id="dry-run",
        nb_tokens_by_category={},
        unit_costs={},
    )


def _free_model_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    """A free/zero-price model: real tokens, no unit costs -> tokens but zero cost."""
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="ollama-x",
        inference_model_id="ollama-x-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={},
    )


class TestRenderRunCostReport:
    def _set_channels(self, mocker: MockerFixture, *, console: bool, csv: bool, csv_dir: Path | None = None) -> None:
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", console)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", csv)
        if csv_dir is not None:
            mocker.patch.object(reporting_config, "cost_report_dir_path", str(csv_dir))

    def test_no_op_when_costs_off(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=False)

        spy.assert_not_called()

    def test_no_op_when_tokens_none(self, mocker: MockerFixture) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=None, is_generate_costs=True)

        spy.assert_not_called()

    def test_no_op_when_tokens_empty(self, mocker: MockerFixture) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[], is_generate_costs=True)

        spy.assert_not_called()

    def test_no_op_when_no_reportable_usage(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        """A dry-run-shaped usage (zero tokens, zero cost) does no reportable work -> no report, channels on."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_zero_cost_usage(job_metadata)], is_generate_costs=True)

        spy.assert_not_called()

    def test_renders_free_model_with_tokens(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        """A free/zero-price model with real tokens IS reported (cost 0) — not suppressed like a dry run."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=False)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_free_model_usage(job_metadata)], is_generate_costs=True)

        spy.assert_called_once()
        aggregated = spy.call_args.args[0]
        assert aggregated.total_cost == 0.0
        assert aggregated.total_nb_tokens == 150

    def test_no_op_when_both_channels_off(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=False, csv=False)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)

        spy.assert_not_called()

    def test_console_channel_only(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=True, csv=False)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)

        spy.assert_called_once()
        assert spy.call_args.args[0].total_cost == 0.2  # the aggregated total, computed once
        kwargs = spy.call_args.kwargs
        assert kwargs["pipeline_run_id"] == _RUN_ID
        assert kwargs["print_to_console"] is True
        assert kwargs["cost_report_file_path"] is None

    def test_csv_channel_only(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._set_channels(mocker, console=False, csv=True, csv_dir=tmp_path)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)

        spy.assert_called_once()
        kwargs = spy.call_args.kwargs
        assert kwargs["print_to_console"] is False
        cost_report_file_path = kwargs["cost_report_file_path"]
        assert cost_report_file_path is not None
        assert Path(cost_report_file_path).parent == tmp_path

    @pytest.mark.parametrize(
        "render_error",
        [
            UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed"),
            CostRegistryError("aggregation blew up"),
            OSError("disk full while writing CSV"),
        ],
    )
    def test_render_failure_never_fails_the_run(self, mocker: MockerFixture, job_metadata: JobMetadata, render_error: Exception) -> None:
        """A reporting-side failure (UTF-8 CSV encode, cost-registry, or I/O) is caught — the run still succeeds."""
        mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report", side_effect=render_error)
        self._set_channels(mocker, console=True, csv=False)

        # Must not raise: the guard degrades the failure to a warning rather than failing the successful run.
        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)
