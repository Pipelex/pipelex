"""Integration tests for the Phase-1 emit-gate wiring in :func:`pipeline_run_setup`.

Pins that the two concerns are decoupled at setup time over the shared event-log transport:

- **costs-only (``--no-graph --costs``):** the tracer is still opened (so node ids are minted), the
  returned graph_context carries ``emit_graph_events=False`` / ``emit_usage_events=True``, and the
  usage event-log context IS registered on the report delegate (``set_event_log``).
- **graph-only (``--graph --no-costs``):** the returned graph_context carries
  ``emit_graph_events=True`` / ``emit_usage_events=False`` and the usage event-log context is NOT
  registered (so usage events are suppressed).

These assert the gating decisions D4/D5/D6 land on the run's GraphContext and the report delegate,
without needing an actual inference run.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import clear_current_library, get_library_manager, get_report_delegate
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend

_GATE_DOMAIN = "prs_emit_gates"
_GATE_MTHDS = f"""
domain = "{_GATE_DOMAIN}"
description = "Minimal bundle for pipeline_run_setup emit-gate tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to set up a PipeJob"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _config(*, generate_graph: bool, generate_costs: bool) -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=generate_graph,
        generate_costs=generate_costs,
        mock_inputs=True,
    )


def _cleanup(pipeline_run_id: str, library_id: str) -> None:
    """Tear down the per-run state pipeline_run_setup leaves open on the success path.

    The success path intentionally does NOT close the tracer / event-log context; execute_pipeline
    normally owns this teardown. Since this test calls pipeline_run_setup directly, it cleans up itself.
    """
    get_report_delegate().clear_event_log(context_key=pipeline_run_id)
    tracer_manager = GraphTracerManager.get_instance()
    if tracer_manager is not None:
        tracer_manager.close_tracer(pipeline_run_id)
    get_library_manager().teardown(library_id=library_id)
    clear_current_library()


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupEmitGates:
    def _enable_ndjson_tracing(self, mocker: MockerFixture, traces_dir: str) -> None:
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

    async def test_costs_only_registers_usage_log_and_sets_flags(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_costs_only")))
        set_event_log_spy = mocker.spy(get_report_delegate(), "set_event_log")

        pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
            execution_config=_config(generate_graph=False, generate_costs=True),
            mthds_contents=[_GATE_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
        )
        try:
            graph_context = pipe_job.job_metadata.graph_context
            # The tracer is opened in costs-only mode (D5), so the context exists and mints node ids.
            assert graph_context is not None
            assert graph_context.emit_graph_events is False
            assert graph_context.emit_usage_events is True
            # The usage event-log context IS registered for this run (costs on).
            registered_keys = [call.kwargs.get("context_key") for call in set_event_log_spy.call_args_list]
            assert pipeline_run_id in registered_keys
        finally:
            _cleanup(pipeline_run_id, library_id)

    async def test_graph_only_does_not_register_usage_log(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_graph_only")))
        set_event_log_spy = mocker.spy(get_report_delegate(), "set_event_log")

        pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
            execution_config=_config(generate_graph=True, generate_costs=False),
            mthds_contents=[_GATE_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
        )
        try:
            graph_context = pipe_job.job_metadata.graph_context
            assert graph_context is not None
            assert graph_context.emit_graph_events is True
            assert graph_context.emit_usage_events is False
            # No usage event-log context registered for this run (costs off) -> usage events suppressed.
            registered_keys = [call.kwargs.get("context_key") for call in set_event_log_spy.call_args_list]
            assert pipeline_run_id not in registered_keys
        finally:
            _cleanup(pipeline_run_id, library_id)
