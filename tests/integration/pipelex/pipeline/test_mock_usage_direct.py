"""Integration tests for the ``is_mock_usage`` dry sub-flag in DIRECT mode.

A dry run with ``is_mock_usage=True`` keeps the dry contract (no provider, no spend, leaf mocks) but
emits *reportable* (non-zero) synthetic usage. These tests prove the end-to-end contract:

- The leaf never reaches the LLM worker (``get_llm_worker`` is not called).
- Usage rides back on ``PipeOutput.tokens_usages`` under the ``mock_usage`` sentinel model, with
  non-zero tokens — so ``AggregatedCosts.has_reportable_usage`` is True and the cost report renders
  (unlike the default dry run, whose zero-token usage is deliberately suppressed).

Both the text path and the structured-object path are covered. NDJSON tracing is enabled so the
usage events assemble onto ``PipeOutput``.
"""

import io

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from pipelex.cogt.content_generation.dry_mock import MOCK_USAGE_MODEL_NAME
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.reporting.cost_report_renderer import render_run_cost_report
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode

_DOMAIN = "mock_usage_direct"
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "Minimal bundle for is_mock_usage DIRECT tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.write_text]
type = "PipeLLM"
description = "Pipe that outputs plain text"
inputs = {{ subject = "Text" }}
output = "Text"
prompt = "Write about $subject"

[pipe.write_topic]
type = "PipeLLM"
description = "Pipe that outputs a structured Topic"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Make a topic from $subject"
"""


def _recording_console() -> Console:
    return Console(record=True, file=io.StringIO(), width=400)


@pytest.mark.asyncio(loop_scope="class")
class TestMockUsageDirect:
    def _enable_ndjson_tracing(self, mocker: MockerFixture, traces_dir: str) -> None:
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

    def _config(self) -> PipelineExecutionConfig:
        # Costs on (default) so usage assembles; mock_inputs fills the `subject` input for the dry run.
        return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=False,
            generate_usage=True,
            mock_inputs=True,
        )

    async def _run_mock_usage(self, pipe_code: str) -> PipeOutput:
        # A DRY run; is_mock_usage switches the leaf reporting to non-zero synthetic usage.
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, is_mock_usage=True, execution_config=self._config())
        response = await runner.execute(pipe_code=pipe_code, mthds_contents=[_MTHDS])
        return response.pipe_output

    async def test_text_pipe_mocks_leaf_and_assembles_reportable_usage(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """A dry text pipe under is_mock_usage never calls the worker, yet assembles non-zero usage."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_mock_text")))
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")

        pipe_output = await self._run_mock_usage("write_text")

        worker_spy.assert_not_called()  # no provider call -> no spend
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        assert all(usage.inference_model_name == MOCK_USAGE_MODEL_NAME for usage in pipe_output.tokens_usages)

        aggregated = CostRegistry.aggregate_costs(pipe_output.tokens_usages)
        assert aggregated.has_reportable_usage  # non-zero tokens -> the report is NOT suppressed
        assert aggregated.total_nb_tokens > 0

    async def test_object_pipe_mocks_leaf_and_assembles_reportable_usage(
        self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture
    ) -> None:
        """The structured-object path also fakes the leaf and reports non-zero usage."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_mock_object")))
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")

        pipe_output = await self._run_mock_usage("write_topic")

        worker_spy.assert_not_called()
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        aggregated = CostRegistry.aggregate_costs(pipe_output.tokens_usages)
        assert aggregated.has_reportable_usage
        # The structured output was produced by the mock object builder (a Topic with a name).
        main_stuff = pipe_output.working_memory.get_main_stuff()
        assert main_stuff is not None

    async def test_cost_report_renders_for_mock_usage(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """The end-of-run cost report RENDERS for an is_mock_usage run (non-suppressed), under the sentinel model."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_mock_render")))
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        reporting_config = get_config().pipelex.reporting_config
        mocker.patch.object(reporting_config, "is_log_costs_to_console", True)
        mocker.patch.object(reporting_config, "is_generate_cost_report_file_enabled", False)
        console = _recording_console()
        mocker.patch("pipelex.cogt.usage.cost_registry.get_console", return_value=console)

        pipe_output = await self._run_mock_usage("write_text")

        render_run_cost_report(
            pipeline_run_id=pipe_output.pipeline_run_id,
            tokens_usages=pipe_output.tokens_usages,
            is_generate_costs=True,
        )
        rendered = console.export_text()
        assert MOCK_USAGE_MODEL_NAME in rendered  # the table is shown (NOT suppressed like a default dry run)
        assert "Total" in rendered
