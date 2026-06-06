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
    """Pins that the runner fallback honors graph_context.emit_usage_events."""

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
