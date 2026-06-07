"""Unit tests for ReportingManager event emission.

Validates that when an EventLogProtocol is provided, ReportingManager emits
UsageReportEvent with per-context isolation for concurrent workflows.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.trace_context import TraceContext
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import UsageReportEvent

DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)


def _make_test_llm_job(
    pipeline_run_id: str,
    trace_context: TraceContext | None = None,
) -> LLMJob:
    """Create a minimal LLMJob for testing event emission."""
    now = datetime.now(timezone.utc)
    job_metadata = JobMetadata(
        user_id="test_user",
        pipeline_run_id=pipeline_run_id,
        trace_context=trace_context,
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


def _make_trace_context(
    graph_id: str,
    parent_node_id: str | None = None,
    tracer_key: str | None = None,
    node_sequence: int = 0,
) -> TraceContext:
    """Create a TraceContext for testing with lookup_key resolution."""
    return TraceContext(
        graph_id=graph_id,
        tracer_key=tracer_key,
        parent_node_id=parent_node_id,
        node_sequence=node_sequence,
        data_inclusion=DATA_INCLUSION_OFF,
    )


class TestReportingEventEmission:
    """Tests for ReportingManager usage event emission with per-context isolation."""

    PIPELINE_RUN_ID = "run_rpt_001"
    WORKFLOW_ID = "wf_rpt_abc"

    def _make_reporting_manager_with_event_log(self) -> tuple[ReportingManager, InMemoryEventLog]:
        """Create a ReportingManager configured with an event log.

        The context_key is PIPELINE_RUN_ID, matching the lookup_key of TraceContexts
        created with graph_id=PIPELINE_RUN_ID and no tracer_key.
        """
        event_log = InMemoryEventLog()
        manager = ReportingManager()
        manager.setup()
        manager.set_event_log(
            context_key=self.PIPELINE_RUN_ID,
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
        )
        return manager, event_log

    # ------------------------------------------------------------------
    # Existing tests (updated for context-based resolution)
    # ------------------------------------------------------------------

    def test_report_inference_job_emits_usage_event(self) -> None:
        """UsageReportEvent is emitted when reporting an LLM inference job with event_log set."""
        manager, event_log = self._make_reporting_manager_with_event_log()

        trace_context = _make_trace_context(graph_id=self.PIPELINE_RUN_ID)
        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID, trace_context=trace_context)
        manager.report_inference_job(llm_job)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == 100
        assert usage_events[0].node_id == "unknown"  # No trace_context parent set

    def test_report_inference_job_captures_node_id_from_trace_context(self) -> None:
        """UsageReportEvent captures the parent node_id from graph context."""
        manager, event_log = self._make_reporting_manager_with_event_log()

        trace_context = _make_trace_context(
            graph_id=self.PIPELINE_RUN_ID,
            parent_node_id="test-graph:node_42",
            node_sequence=43,
        )

        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID, trace_context=trace_context)
        manager.report_inference_job(llm_job)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].node_id == "test-graph:node_42"
        assert usage_events[0].workflow_id == self.WORKFLOW_ID

    @pytest.mark.parametrize(
        "emit_error",
        [
            ClientError(
                error_response={"Error": {"Code": "ProvisionedThroughputExceededException"}},
                operation_name="PutItem",
            ),
            OSError("disk full"),
        ],
        ids=["client_error", "os_error"],
    )
    def test_registered_context_emit_failure_is_best_effort(
        self,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        emit_error: Exception,
    ) -> None:
        """A backend emit failure on the registered-context fast path is dropped with a WARNING, never raised.

        report_inference_job runs synchronously after the inference has already succeeded (and been
        billed), so a transient event-log write failure — DynamoDB throttle/auth/timeout (ClientError)
        or NDJSON disk error (OSError) — must not propagate and turn a successful inference into a
        failed pipeline. Mirrors the runner-fallback contract in test_emit_runner_fallback.
        """
        manager, event_log = self._make_reporting_manager_with_event_log()
        mocker.patch.object(event_log, "emit", side_effect=emit_error)

        trace_context = _make_trace_context(graph_id=self.PIPELINE_RUN_ID)
        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID, trace_context=trace_context)

        with caplog.at_level(logging.WARNING):
            # Must not raise — the failure is logged and dropped.
            manager.report_inference_job(llm_job)

        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_setup_and_teardown_without_event_log(self) -> None:
        """Without any event_log registered, setup/teardown are inert and report_inference_job no-ops."""
        manager = ReportingManager()
        manager.setup()

        # A job whose trace_context is None must not emit anything and must not raise.
        manager.report_inference_job(_make_test_llm_job("direct_run", trace_context=None))

        manager.teardown()
        assert len(manager._event_log_contexts) == 0  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    # ------------------------------------------------------------------
    # Per-context isolation regression tests
    # ------------------------------------------------------------------

    def test_concurrent_contexts_are_isolated(self) -> None:
        """Two concurrent contexts emit events to their own event logs without interference."""
        event_log_a = InMemoryEventLog()
        event_log_b = InMemoryEventLog()
        manager = ReportingManager()
        manager.setup()

        manager.set_event_log(context_key="wf_a", event_log=event_log_a, workflow_id="wf_a", pipeline_run_id="run_a")
        manager.set_event_log(context_key="wf_b", event_log=event_log_b, workflow_id="wf_b", pipeline_run_id="run_b")

        ctx_a = _make_trace_context(graph_id="run_a", tracer_key="wf_a")
        ctx_b = _make_trace_context(graph_id="run_b", tracer_key="wf_b")

        job_a = _make_test_llm_job("run_a", trace_context=ctx_a)
        job_b = _make_test_llm_job("run_b", trace_context=ctx_b)

        manager.report_inference_job(job_a)
        manager.report_inference_job(job_b)

        events_a = [evt for evt in event_log_a.read_events("run_a") if isinstance(evt, UsageReportEvent)]
        events_b = [evt for evt in event_log_b.read_events("run_b") if isinstance(evt, UsageReportEvent)]
        assert len(events_a) == 1
        assert events_a[0].workflow_id == "wf_a"
        assert events_a[0].pipeline_run_id == "run_a"
        assert len(events_b) == 1
        assert events_b[0].workflow_id == "wf_b"
        assert events_b[0].pipeline_run_id == "run_b"

    def test_clear_event_log_removes_only_target_context(self) -> None:
        """Clearing one context does not affect another."""
        event_log_a = InMemoryEventLog()
        event_log_b = InMemoryEventLog()
        manager = ReportingManager()
        manager.setup()

        manager.set_event_log(context_key="wf_a", event_log=event_log_a, workflow_id="wf_a", pipeline_run_id="run_a")
        manager.set_event_log(context_key="wf_b", event_log=event_log_b, workflow_id="wf_b", pipeline_run_id="run_b")

        # Clear context A before any emission
        manager.clear_event_log(context_key="wf_a")

        ctx_a = _make_trace_context(graph_id="run_a", tracer_key="wf_a")
        ctx_b = _make_trace_context(graph_id="run_b", tracer_key="wf_b")

        job_a = _make_test_llm_job("run_a", trace_context=ctx_a)
        job_b = _make_test_llm_job("run_b", trace_context=ctx_b)

        manager.report_inference_job(job_a)  # Should NOT emit (context cleared)
        manager.report_inference_job(job_b)  # Should emit

        events_a = [evt for evt in event_log_a.read_events("run_a") if isinstance(evt, UsageReportEvent)]
        events_b = [evt for evt in event_log_b.read_events("run_b") if isinstance(evt, UsageReportEvent)]
        assert len(events_a) == 0
        assert len(events_b) == 1

    def test_no_trace_context_skips_emission(self) -> None:
        """Jobs without trace_context skip event emission even when event logs are configured."""
        manager, event_log = self._make_reporting_manager_with_event_log()

        llm_job = _make_test_llm_job(self.PIPELINE_RUN_ID, trace_context=None)
        manager.report_inference_job(llm_job)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 0

    def test_clear_event_log_is_idempotent(self) -> None:
        """Calling clear_event_log for a non-existent key does not raise."""
        manager = ReportingManager()
        manager.setup()
        manager.clear_event_log(context_key="nonexistent")  # Should not raise

    def test_teardown_clears_all_contexts(self) -> None:
        """teardown() removes all event log contexts."""
        manager, _event_log = self._make_reporting_manager_with_event_log()
        manager.teardown()
        assert len(manager._event_log_contexts) == 0  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def test_sequence_counters_are_independent(self) -> None:
        """Each context maintains its own monotonic sequence counter."""
        event_log_a = InMemoryEventLog()
        event_log_b = InMemoryEventLog()
        manager = ReportingManager()
        manager.setup()

        manager.set_event_log(context_key="wf_a", event_log=event_log_a, workflow_id="wf_a", pipeline_run_id="run_a")
        manager.set_event_log(context_key="wf_b", event_log=event_log_b, workflow_id="wf_b", pipeline_run_id="run_b")

        ctx_a = _make_trace_context(graph_id="run_a", tracer_key="wf_a")
        ctx_b = _make_trace_context(graph_id="run_b", tracer_key="wf_b")

        # Emit 3 events for context A, 1 for context B
        for _index in range(3):
            manager.report_inference_job(_make_test_llm_job("run_a", trace_context=ctx_a))
        manager.report_inference_job(_make_test_llm_job("run_b", trace_context=ctx_b))

        events_a = [evt for evt in event_log_a.read_events("run_a") if isinstance(evt, UsageReportEvent)]
        events_b = [evt for evt in event_log_b.read_events("run_b") if isinstance(evt, UsageReportEvent)]
        assert [evt.sequence for evt in events_a] == [0, 1, 2]
        assert [evt.sequence for evt in events_b] == [0]

    def test_no_emit_when_no_event_log_set_and_no_fallback_yet(self, mocker: MockerFixture) -> None:
        """Pin the tracing-disabled silent baseline.

        When set_event_log is never called and tracing_config.is_enabled=False,
        report_inference_job must not write any event anywhere — even after the
        Phase 2 fallback lands. The fallback path is only allowed to engage when
        tracing is enabled.
        """
        # Force tracing to disabled regardless of process config.
        mocker.patch.object(get_config().pipelex.tracing_config, "is_enabled", False)

        manager = ReportingManager()
        manager.setup()

        trace_context = _make_trace_context(graph_id="run_silent", tracer_key="wf_silent", parent_node_id="g:node_0")
        llm_job = _make_test_llm_job("run_silent", trace_context=trace_context)
        manager.report_inference_job(llm_job)

        # No event log was ever set; no event should have been emitted anywhere.
        assert len(manager._event_log_contexts) == 0  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
