"""Unit tests for the one-arg submitter helper ``render_cost_report_for_output``.

The helper is a thin convenience over ``render_run_cost_report``: it unpacks the three primitive
arguments from a finished ``PipeOutput`` and — crucially — derives the ``--costs`` gate from the
output itself (``tokens_usages is None`` exactly when cost reporting was off), not from global config.
These tests pin that derivation and the no-op/render outcomes it produces.
"""

from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.reporting.cost_report_renderer import render_cost_report_for_output
from pipelex.system.job_metadata import JobMetadata

_RUN_ID = "output-helper-run"


def _usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
    )


class TestRenderCostReportForOutput:
    def _enable_channels(self, mocker: MockerFixture) -> None:
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", True)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", False)

    def test_no_op_when_tokens_usages_none(self, mocker: MockerFixture) -> None:
        """tokens_usages is None encodes 'cost reporting was off' -> the derived gate is False -> no render."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._enable_channels(mocker)

        render_cost_report_for_output(PipeOutput(pipeline_run_id=_RUN_ID, tokens_usages=None))

        spy.assert_not_called()

    def test_no_op_when_tokens_usages_empty(self, mocker: MockerFixture) -> None:
        """An empty list (costs on, no inference) is not None, but the primitive's `not tokens_usages` guard no-ops."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._enable_channels(mocker)

        render_cost_report_for_output(PipeOutput(pipeline_run_id=_RUN_ID, tokens_usages=[]))

        spy.assert_not_called()

    def test_renders_with_output_run_id_when_usage_present(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        """A non-empty tokens_usages derives the gate True and renders, titled with the output's own run id."""
        spy = mocker.patch("pipelex.reporting.cost_report_renderer.CostRegistry.render_report")
        self._enable_channels(mocker)

        render_cost_report_for_output(PipeOutput(pipeline_run_id=_RUN_ID, tokens_usages=[_usage(job_metadata)]))

        spy.assert_called_once()
        kwargs = spy.call_args.kwargs
        assert kwargs["pipeline_run_id"] == _RUN_ID
        assert kwargs["cost_report_file_path"] is None
