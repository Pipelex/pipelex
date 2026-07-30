"""Integration tests for in-memory graph tracing via `scoped_event_log` (direct mode).

A dry-run-with-graph executed under ``with scoped_event_log(InMemoryEventLog())`` must:

- produce a non-empty, correct ``GraphSpec`` on ``pipe_output``;
- write NO NDJSON file and touch NO configured backend (the factory is never called —
  the scoped instance is the single transport);
- emit and assemble against the SAME instance (the fix for the two-instance problem);
- assemble the graph even when ``tracing_config.is_enabled`` is False — a set override
  implies tracing-enabled (decision D1);
- keep concurrently-scoped runs isolated from each other.
"""

import asyncio
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog

_SCOPED_DOMAIN = "scoped_in_memory_tracing"
_SCOPED_MTHDS = f"""
domain = "{_SCOPED_DOMAIN}"
description = "Minimal bundle for scoped in-memory tracing tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used to exercise scoped in-memory tracing"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestScopedInMemoryTracing:
    def _forbid_event_log_factory(self, mocker: MockerFixture) -> None:
        """Make any call to make_event_log fail loudly — the scoped instance must be the only transport."""
        factory_error = AssertionError("make_event_log must not be called when a scoped event log is set")
        mocker.patch("pipelex.pipeline.pipeline_run_setup.make_event_log", side_effect=factory_error)
        mocker.patch("pipelex.pipe_run.tracing_assembly.make_event_log", side_effect=factory_error)

    async def _run_dry_with_graph(self) -> PipeOutput:
        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=True,
            mock_inputs=True,
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute(pipe_code="echo_topic", mthds_contents=[_SCOPED_MTHDS])
        return response.pipe_output

    async def test_in_memory_graph_same_instance_no_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With NDJSON tracing configured, the scoped log wins: graph assembles in memory, zero file I/O."""
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))
        self._forbid_event_log_factory(mocker)

        event_log = InMemoryEventLog()
        emit_spy = mocker.spy(event_log, "emit")
        read_spy = mocker.spy(event_log, "read_events")

        with scoped_event_log(event_log):
            pipe_output = await self._run_dry_with_graph()

        # (a) non-empty, correct GraphSpec
        assert pipe_output.graph_spec is not None
        assert len(pipe_output.graph_spec.nodes) >= 1
        assert pipe_output.graph_spec.graph_id == pipe_output.pipeline_run_id
        assert pipe_output.graph_assembly_error is None

        # (b) no NDJSON file, no configured backend touched
        assert list(traces_dir.iterdir()) == []

        # (c) emit and assemble hit the SAME instance
        assert emit_spy.call_count >= 1
        assert read_spy.call_count >= 1
        assert event_log.read_events(pipe_output.pipeline_run_id)

    async def test_override_implies_enabled_when_tracing_disabled(self, mocker: MockerFixture) -> None:
        """D1 regression: is_enabled=False + scoped override → the GraphSpec still assembles in memory."""
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", False)
        self._forbid_event_log_factory(mocker)

        event_log = InMemoryEventLog()
        with scoped_event_log(event_log):
            pipe_output = await self._run_dry_with_graph()

        assert pipe_output.graph_spec is not None
        assert len(pipe_output.graph_spec.nodes) >= 1
        assert event_log.read_events(pipe_output.pipeline_run_id)

    async def test_concurrent_scoped_runs_do_not_cross_contaminate(self, mocker: MockerFixture) -> None:
        """Two concurrently-scoped runs each trace into their own log, with no shared/merged events."""
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", False)
        self._forbid_event_log_factory(mocker)

        log_alpha = InMemoryEventLog(writer_id="alpha")
        log_beta = InMemoryEventLog(writer_id="beta")

        async def scoped_run(event_log: InMemoryEventLog) -> PipeOutput:
            with scoped_event_log(event_log):
                return await self._run_dry_with_graph()

        output_alpha, output_beta = await asyncio.gather(scoped_run(log_alpha), scoped_run(log_beta))

        assert output_alpha.graph_spec is not None
        assert output_beta.graph_spec is not None
        assert output_alpha.pipeline_run_id != output_beta.pipeline_run_id
        assert output_alpha.graph_spec.graph_id != output_beta.graph_spec.graph_id

        # Each log holds only its own run's events.
        assert log_alpha.read_events(output_alpha.pipeline_run_id)
        assert log_alpha.read_events(output_beta.pipeline_run_id) == []
        assert log_beta.read_events(output_beta.pipeline_run_id)
        assert log_beta.read_events(output_alpha.pipeline_run_id) == []
