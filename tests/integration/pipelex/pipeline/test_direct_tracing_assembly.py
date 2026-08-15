"""Integration tests for the Phase-2 DIRECT tracing assembly onto PipeOutput.

A real (dry, no-spend) run through :meth:`PipelexMTHDSProtocol.execute` must ride the assembled
artifacts back on ``pipe_output``:

- **costs on:** ``pipe_output.tokens_usages`` is populated from the run's emitted usage events.
- **costs-only (``--no-graph --costs``):** usage is populated but ``graph_spec`` stays None (F1 — the
  decoupled event stream must not produce a node-less GraphSpec under ``--no-graph``).
- **graph-only (``--graph --no-costs``):** ``graph_spec`` is populated but ``tokens_usages`` stays None.
- **E1:** costs-only mode does not pay the per-pipe stuff serialization that only feeds the GraphSpec.

These run fully dry (``PipeRunMode.DRY`` + ``mock_inputs``) so no inference happens; the dry content
generator still reports token usage inline, which is what populates the usage stream.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.graph.graphspec import GraphSpecMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode

_DIRECT_DOMAIN = "direct_tracing_assembly"
_DIRECT_MTHDS = f"""
domain = "{_DIRECT_DOMAIN}"
description = "Minimal bundle for DIRECT tracing assembly tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used to exercise DIRECT tracing assembly"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _config(*, generate_graph: bool, generate_usage: bool, full_data: bool = False) -> PipelineExecutionConfig:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=generate_graph,
        generate_usage=generate_usage,
        mock_inputs=True,
        force_include_full_data=full_data or None,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestDirectTracingAssembly:
    def _enable_ndjson_tracing(self, mocker: MockerFixture, traces_dir: str) -> None:
        cfg = get_config().runtime.tracing
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

    async def _run(self, execution_config: PipelineExecutionConfig) -> PipeOutput:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute(pipe_code="echo_topic", mthds_contents=[_DIRECT_MTHDS])
        return response.pipe_output

    async def test_costs_on_populates_tokens_usages(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_costs_on")))

        pipe_output = await self._run(_config(generate_graph=True, generate_usage=True))

        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        assert pipe_output.graph_spec is not None
        assert pipe_output.graph_spec.meta["mode"] == GraphSpecMode.DRY
        assert pipe_output.usage_assembly_error is None

    async def test_costs_only_leaves_graph_spec_none(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """F1 (DIRECT): a costs-only run must not produce a node-less GraphSpec under --no-graph."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_costs_only")))

        pipe_output = await self._run(_config(generate_graph=False, generate_usage=True))

        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        assert pipe_output.graph_spec is None

    async def test_graph_only_leaves_tokens_usages_none(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_graph_only")))

        pipe_output = await self._run(_config(generate_graph=True, generate_usage=False))

        assert pipe_output.graph_spec is not None
        assert pipe_output.tokens_usages is None

    async def test_graph_mode_serializes_stuff_payloads(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """Baseline for E1: with graph events + full data inclusion, the per-pipe HTML payload IS built."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_graph_full")))
        render_spy = mocker.spy(StuffContent, "rendered_pretty_html")

        await self._run(_config(generate_graph=True, generate_usage=True, full_data=True))

        assert render_spy.call_count >= 1

    async def test_costs_only_skips_stuff_serialization(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """E1: in costs-only mode the per-pipe HTML payload (graph-only) is never built, even with full data inclusion."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_costs_full")))
        render_spy = mocker.spy(StuffContent, "rendered_pretty_html")

        pipe_output = await self._run(_config(generate_graph=False, generate_usage=True, full_data=True))

        assert render_spy.call_count == 0
        # And the usage still rode back — the optimization didn't break cost reporting.
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
