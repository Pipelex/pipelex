"""Integration tests for the Phase-3 event-sourced cost-report rendering.

These cover the cutover from the live registry to ``PipeOutput`` as the cost source:

- A real (dry, no-spend) DIRECT run renders the cost table from ``pipe_output.tokens_usages``,
  and the usage assembled onto ``PipeOutput`` matches the still-present registry for the same run
  (numeric-fidelity guard during the transition; the registry is removed in Phase 4).
- ``--no-costs`` assembles no usage, so the renderer is a no-op (nothing printed).
- Hand-built usage proves the table and CSV channels render correct *non-zero* totals (the dry path
  reports zero-token synthetic usage, so non-zero totals can't come from a dry run).
"""

import io
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_report_delegate
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.runner import PipelexRunner
from pipelex.reporting.cost_report_renderer import render_run_cost_report
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend

_DOMAIN = "cost_report_rendering"
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "Minimal bundle for cost-report rendering tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used to exercise cost-report rendering"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _recording_console() -> Console:
    return Console(record=True, file=io.StringIO(), width=400)


def _non_zero_usage(job_metadata: JobMetadata) -> LLMTokensUsage:
    # INPUT 100 @ $1/M + OUTPUT 50 @ $2/M -> total cost 0.2000.
    return LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
    )


@pytest.mark.asyncio(loop_scope="class")
class TestCostReportRendering:
    def _enable_ndjson_tracing(self, mocker: MockerFixture, traces_dir: str) -> None:
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

    def _config(self, *, generate_costs: bool) -> PipelineExecutionConfig:
        return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=False,
            generate_costs=generate_costs,
            mock_inputs=True,
        )

    async def _run(self, execution_config: PipelineExecutionConfig) -> PipeOutput:
        runner = PipelexRunner(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute_pipeline(pipe_code="echo_topic", mthds_contents=[_MTHDS])
        return response.pipe_output

    async def test_renders_correct_non_zero_totals(self, mocker: MockerFixture, job_metadata: JobMetadata) -> None:
        """Hand-built usage: the console channel renders the model, totals, and total cost."""
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", True)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", False)
        console = _recording_console()
        mocker.patch("pipelex.cogt.usage.cost_registry.get_console", return_value=console)

        render_run_cost_report(pipeline_run_id="hand-built", tokens_usages=[_non_zero_usage(job_metadata)], is_generate_costs=True)

        rendered = console.export_text()
        assert "test-model" in rendered
        assert "Total" in rendered
        assert "0.2000" in rendered  # 100 input @ $1/M + 50 output @ $2/M

    async def test_csv_channel_writes_file(self, mocker: MockerFixture, job_metadata: JobMetadata, tmp_path: Path) -> None:
        """The CSV channel writes a populated report file under the configured directory."""
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", False)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", True)
        mocker.patch.object(reporting_config, "cost_report_dir_path", str(tmp_path))

        render_run_cost_report(pipeline_run_id="csv-run", tokens_usages=[_non_zero_usage(job_metadata)], is_generate_costs=True)

        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1
        contents = csv_files[0].read_text(encoding="utf-8")
        assert "test-model" in contents

    async def test_direct_dry_run_suppresses_table_but_populates_usage(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """A DIRECT dry run assembles (zero-token) usage onto PipeOutput and matches the still-present
        registry, but the renderer prints NOTHING because the total cost is zero (no zero-cost table).
        """
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_render")))
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", True)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", False)
        console = _recording_console()
        mocker.patch("pipelex.cogt.usage.cost_registry.get_console", return_value=console)

        pipe_output = await self._run(self._config(generate_costs=True))

        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1

        render_run_cost_report(
            pipeline_run_id=pipe_output.pipeline_run_id,
            tokens_usages=pipe_output.tokens_usages,
            is_generate_costs=True,
        )
        # Dry runs emit zero-token synthetic usage -> total cost 0 -> no table printed.
        assert console.export_text() == ""

        # Fidelity: the live registry (still populated in parallel until Phase 4) holds the same
        # count of records as the usage assembled onto PipeOutput for this run.
        registries = getattr(get_report_delegate(), "_usage_registries", None)
        assert registries is not None, "DIRECT mode must keep a ReportingManager with per-run registries"
        registry = registries.get(pipe_output.pipeline_run_id)
        assert registry is not None
        assert len(registry.get_current_tokens_usage()) == len(pipe_output.tokens_usages)

    async def test_no_costs_renders_nothing(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """--no-costs assembles no usage, so the renderer prints nothing."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_no_costs")))
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", True)
        console = _recording_console()
        mocker.patch("pipelex.cogt.usage.cost_registry.get_console", return_value=console)

        pipe_output = await self._run(self._config(generate_costs=False))

        assert pipe_output.tokens_usages is None

        render_run_cost_report(
            pipeline_run_id=pipe_output.pipeline_run_id,
            tokens_usages=pipe_output.tokens_usages,
            is_generate_costs=False,
        )
        assert console.export_text() == ""
