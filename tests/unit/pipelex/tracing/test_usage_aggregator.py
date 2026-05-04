"""Tests for UsageAggregator."""

from datetime import datetime, timezone
from typing import Any

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import NodeKind
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata, UnitJobId
from pipelex.tracing.trace_events import PipeStartEvent, TraceEvent, UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator

_TIMESTAMP = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
_PIPELINE_RUN_ID = "run_001"
_WORKFLOW_ID = "wf_abc"


def _make_llm_tokens_usage(model_name: str = "claude-sonnet") -> LLMTokensUsage:
    return LLMTokensUsage(
        job_metadata=JobMetadata(
            user_id="user_test",
            pipeline_run_id=_PIPELINE_RUN_ID,
            pipe_code="test_pipe",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        ),
        inference_model_name=model_name,
        unit_costs={CostCategory.INPUT: 0.003, CostCategory.OUTPUT: 0.015},
        inference_model_id="claude-sonnet-4-20250514",
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )


def _make_base_fields(sequence: int = 0) -> dict[str, Any]:
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": _WORKFLOW_ID,
        "timestamp": _TIMESTAMP,
        "sequence": sequence,
    }


def _make_usage_event(sequence: int, model_name: str = "claude-sonnet") -> UsageReportEvent:
    return UsageReportEvent(
        **_make_base_fields(sequence),
        node_id=f"graph_1:{_WORKFLOW_ID}:node_{sequence}",
        tokens_usage=_make_llm_tokens_usage(model_name),
    )


def _make_pipe_start_event(sequence: int) -> PipeStartEvent:
    return PipeStartEvent(
        **_make_base_fields(sequence),
        node_id=f"graph_1:{_WORKFLOW_ID}:node_{sequence}",
        pipe_code="test_pipe",
        pipe_type="PipeLLMGenText",
        node_kind=NodeKind.OPERATOR,
    )


class TestUsageAggregator:
    """Tests for UsageAggregator.aggregate()."""

    def test_collects_all_usage_events(self) -> None:
        """Mixed event types — only UsageReportEvent tokens extracted."""
        events: list[TraceEvent] = [
            _make_pipe_start_event(0),
            _make_usage_event(1, model_name="claude-sonnet"),
            _make_pipe_start_event(2),
            _make_usage_event(3, model_name="gpt-4"),
        ]

        result = UsageAggregator.aggregate(events)

        assert len(result) == 2
        assert result[0].inference_model_name == "claude-sonnet"
        assert result[1].inference_model_name == "gpt-4"

    def test_empty_events_returns_empty_list(self) -> None:
        """No events produces empty list."""
        result = UsageAggregator.aggregate([])
        assert result == []

    def test_ignores_non_usage_events(self) -> None:
        """Only non-usage events → empty result."""
        events: list[TraceEvent] = [
            _make_pipe_start_event(0),
            _make_pipe_start_event(1),
        ]

        result = UsageAggregator.aggregate(events)
        assert result == []

    def test_preserves_order(self) -> None:
        """Multiple usage events returned in input order."""
        events: list[TraceEvent] = [
            _make_usage_event(0, model_name="model_a"),
            _make_usage_event(1, model_name="model_b"),
            _make_usage_event(2, model_name="model_c"),
        ]

        result = UsageAggregator.aggregate(events)

        assert len(result) == 3
        assert [usage.inference_model_name for usage in result] == ["model_a", "model_b", "model_c"]
