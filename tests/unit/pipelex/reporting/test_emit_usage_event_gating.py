"""Unit tests for the emit_usage_events gate in ReportingManager (Phase 1 decoupling).

Pins the load-bearing decoupling: usage emission is gated by ``graph_context.emit_usage_events``,
independent of graph events. In graph-only mode (``--graph --no-costs``) no usage event-log context
is registered, so reporting lands on the runner fallback — which must suppress the usage event. In
costs-only / default mode the same fallback emits. This is what lets ``--no-graph`` keep cost data
and ``--no-costs`` drop it while both share one event-log transport.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent

DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)


def _make_llm_job(pipeline_run_id: str, graph_context: GraphContext | None) -> LLMJob:
    now = datetime.now(timezone.utc)
    job_metadata = JobMetadata(
        user_id="test_user",
        pipeline_run_id=pipeline_run_id,
        graph_context=graph_context,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        unit_job_id=UnitJobId.LLM_GEN_TEXT,
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )


def _make_graph_context(graph_id: str, *, emit_usage_events: bool, emit_graph_events: bool = True) -> GraphContext:
    return GraphContext(
        graph_id=graph_id,
        tracer_key=f"wf_{graph_id}",
        parent_node_id=f"{graph_id}:node_0",
        node_sequence=0,
        data_inclusion=DATA_INCLUSION_OFF,
        emit_graph_events=emit_graph_events,
        emit_usage_events=emit_usage_events,
    )


def _enable_ndjson_tracing(mocker: MockerFixture, traces_dir: Path) -> None:
    cfg = get_config().pipelex.tracing_config
    mocker.patch.object(cfg, "is_enabled", True)
    mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
    mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))


class TestEmitUsageEventGating:
    """Pins that usage emission honors graph_context.emit_usage_events on BOTH paths.

    The gate lives in the dispatcher (_emit_usage_event), before the context lookup, so it guards the
    fast path (a registered set_event_log context) and the runner fallback alike — correctness no
    longer rests on the cross-file invariant "a context is registered only when costs are on".
    """

    def test_graph_only_suppresses_usage_event(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """--graph --no-costs: emit_usage_events=False -> the runner fallback writes no usage event."""
        ActivityEventLogCache.reset_for_tests()
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()
        graph_context = _make_graph_context("run_graph_only", emit_usage_events=False, emit_graph_events=True)

        manager.report_inference_job(_make_llm_job("run_graph_only", graph_context=graph_context))

        # Nothing emitted anywhere: no usage context was registered (set_event_log skipped) and the
        # fallback returns early on emit_usage_events=False.
        assert list(tmp_path.glob("**/*.ndjson")) == []
        ActivityEventLogCache.reset_for_tests()

    def test_costs_enabled_emits_usage_event_via_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Costs on: emit_usage_events=True -> the runner fallback emits the usage event as before."""
        ActivityEventLogCache.reset_for_tests()
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()
        graph_context = _make_graph_context("run_costs", emit_usage_events=True, emit_graph_events=False)

        manager.report_inference_job(_make_llm_job("run_costs", graph_context=graph_context))

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        usage_events = [evt for evt in reader.read_events("run_costs") if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].pipeline_run_id == "run_costs"
        assert usage_events[0].writer_id.startswith("act_")
        ActivityEventLogCache.reset_for_tests()

    def test_registered_context_suppresses_usage_when_costs_off(self, mocker: MockerFixture) -> None:
        """Fast path: a REGISTERED context with emit_usage_events=False must emit nothing.

        Simulates the leak scenario the hoisted gate defends against — a usage event-log context that
        outlived its run (clear_event_log skipped) and collides on lookup_key with a later graph-only
        run. Without the gate the fast path would emit; the dispatcher's early-return suppresses it.
        """
        manager = ReportingManager()
        manager.setup()
        graph_context = _make_graph_context("run_leaked", emit_usage_events=False, emit_graph_events=True)

        event_log_spy = mocker.MagicMock()
        event_log_spy.writer_id = "leaked_writer"
        event_log_spy.next_sequence.return_value = 0
        manager.set_event_log(
            context_key=graph_context.lookup_key,
            event_log=event_log_spy,
            workflow_id="direct",
            pipeline_run_id="run_leaked",
        )

        manager.report_inference_job(_make_llm_job("run_leaked", graph_context=graph_context))

        event_log_spy.emit.assert_not_called()

    def test_registered_context_emits_when_costs_on(self, mocker: MockerFixture) -> None:
        """Control: with the SAME registration but emit_usage_events=True, the fast path DOES emit.

        Proves the suppression above is the gate's doing, not a mis-wired registration that never
        reaches the fast path.
        """
        manager = ReportingManager()
        manager.setup()
        graph_context = _make_graph_context("run_fastpath", emit_usage_events=True, emit_graph_events=True)

        event_log_spy = mocker.MagicMock()
        event_log_spy.writer_id = "fastpath_writer"
        event_log_spy.next_sequence.return_value = 0
        manager.set_event_log(
            context_key=graph_context.lookup_key,
            event_log=event_log_spy,
            workflow_id="direct",
            pipeline_run_id="run_fastpath",
        )

        manager.report_inference_job(_make_llm_job("run_fastpath", graph_context=graph_context))

        event_log_spy.emit.assert_called_once()
        emitted_event = event_log_spy.emit.call_args.args[0]
        assert isinstance(emitted_event, UsageReportEvent)
        assert emitted_event.pipeline_run_id == "run_fastpath"
        assert emitted_event.writer_id == "fastpath_writer"
