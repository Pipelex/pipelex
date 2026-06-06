"""Unit tests for the Phase-3 end-of-run cost-report renderer.

``render_run_cost_report`` is the single event-sourced renderer both CLIs call: it reads the
usage assembled onto ``pipe_output.tokens_usages`` and renders it through the two D6 channels
(console + CSV), each gated by the reporting config and the resolved ``--costs`` switch.
"""

from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.reporting.cost_report_renderer import render_run_cost_report

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
    """A dry-run-shaped usage: no tokens -> zero cost."""
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="dry-model",
        inference_model_id="dry-run",
        nb_tokens_by_category={},
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
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=False)

        spy.assert_not_called()

    def test_no_op_when_tokens_none(self, mocker: MockerFixture) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=None, is_generate_costs=True)

        spy.assert_not_called()

    def test_no_op_when_tokens_empty(self, mocker: MockerFixture) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[], is_generate_costs=True)

        spy.assert_not_called()

    def test_no_op_when_total_cost_zero(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        """Zero-token (dry-run-shaped) usage costs nothing -> no report, even with channels on."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=True, csv=True)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_zero_cost_usage(job_metadata)], is_generate_costs=True)

        spy.assert_not_called()

    def test_no_op_when_both_channels_off(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=False, csv=False)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)

        spy.assert_not_called()

    def test_console_channel_only(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=True, csv=False)
        usages = [_usage(job_metadata)]

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=usages, is_generate_costs=True)

        spy.assert_called_once()
        kwargs = spy.call_args.kwargs
        assert kwargs["pipeline_run_id"] == _RUN_ID
        assert kwargs["tokens_usages"] is usages
        assert kwargs["print_to_console"] is True
        assert kwargs["cost_report_file_path"] is None

    def test_csv_channel_only(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.generate_report")
        self._set_channels(mocker, console=False, csv=True, csv_dir=tmp_path)

        render_run_cost_report(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)], is_generate_costs=True)

        spy.assert_called_once()
        kwargs = spy.call_args.kwargs
        assert kwargs["print_to_console"] is False
        cost_report_file_path = kwargs["cost_report_file_path"]
        assert cost_report_file_path is not None
        assert Path(cost_report_file_path).parent == tmp_path
