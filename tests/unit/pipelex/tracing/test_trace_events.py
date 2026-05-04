"""Serialization round-trip tests for trace event models."""

from datetime import datetime, timezone
from typing import Any, ClassVar

import pytest
from pydantic import TypeAdapter

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import EdgeKind, ErrorSpec, IOSpec, NodeKind
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata, UnitJobId
from pipelex.tracing.trace_events import (
    AnyTraceEvent,
    BatchAggregateEvent,
    BatchItemEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ExecutionDataEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
    TraceEventKind,
    UsageReportEvent,
)


class _Shared:
    """Shared test data for trace event tests."""

    PIPELINE_RUN_ID = "run_abc123"
    WORKFLOW_ID = "wf_pipe_router_xyz"
    TIMESTAMP = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    NODE_ID = "graph_1:wf_pipe_router_xyz:node_0"
    PARENT_NODE_ID = "graph_1:wf_pipe_router_xyz:node_1"

    @staticmethod
    def make_base_fields(sequence: int = 0) -> dict[str, Any]:
        return {
            "pipeline_run_id": _Shared.PIPELINE_RUN_ID,
            "workflow_id": _Shared.WORKFLOW_ID,
            "timestamp": _Shared.TIMESTAMP,
            "sequence": sequence,
        }

    @staticmethod
    def make_io_spec(name: str = "input_text", digest: str = "abc123") -> IOSpec:
        return IOSpec(
            name=name,
            concept="TextContent",
            content_type="text/plain",
            preview="Hello world",
            size=11,
            digest=digest,
        )

    @staticmethod
    def make_error_spec() -> ErrorSpec:
        return ErrorSpec(
            error_type="LLMError",
            message="Model returned an error",
            stack="Traceback (most recent call last):\n  File ...",
        )

    @staticmethod
    def make_job_metadata() -> JobMetadata:
        return JobMetadata(
            user_id="user_test",
            pipeline_run_id=_Shared.PIPELINE_RUN_ID,
            pipe_code="test_pipe",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        )

    @staticmethod
    def make_llm_tokens_usage() -> LLMTokensUsage:
        return LLMTokensUsage(
            job_metadata=_Shared.make_job_metadata(),
            inference_model_name="claude-sonnet",
            unit_costs={CostCategory.INPUT: 0.003, CostCategory.OUTPUT: 0.015},
            inference_model_id="claude-sonnet-4-20250514",
            nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        )


# Type adapter for the discriminated union
_any_trace_event_adapter: TypeAdapter[TraceEvent] = TypeAdapter(AnyTraceEvent)


class TestTraceEvents:
    """Serialization round-trip and discriminated union tests for trace events."""

    EVENTS_AND_KINDS: ClassVar[list[tuple[str, TraceEventKind, dict[str, Any]]]] = [
        (
            "pipe_start",
            TraceEventKind.PIPE_START,
            {
                "node_id": _Shared.NODE_ID,
                "parent_node_id": _Shared.PARENT_NODE_ID,
                "pipe_code": "gen_summary",
                "pipe_type": "PipeLLM",
                "node_kind": NodeKind.OPERATOR,
                "input_specs": [_Shared.make_io_spec()],
            },
        ),
        (
            "pipe_end_success",
            TraceEventKind.PIPE_END_SUCCESS,
            {
                "node_id": _Shared.NODE_ID,
                "ended_at": _Shared.TIMESTAMP,
                "output_spec": _Shared.make_io_spec(name="output_text", digest="def456"),
                "metrics": {"tokens": 150.0},
            },
        ),
        (
            "pipe_end_error",
            TraceEventKind.PIPE_END_ERROR,
            {
                "node_id": _Shared.NODE_ID,
                "ended_at": _Shared.TIMESTAMP,
                "error": _Shared.make_error_spec(),
            },
        ),
        (
            "edge",
            TraceEventKind.EDGE,
            {
                "edge_id": "graph_1:wf_pipe_router_xyz:edge_0",
                "source_node_id": _Shared.NODE_ID,
                "target_node_id": _Shared.PARENT_NODE_ID,
                "edge_kind": EdgeKind.CONTAINS,
                "label": "child",
                "source_stuff_digest": "abc123",
                "target_stuff_digest": "def456",
            },
        ),
        (
            "controller_output",
            TraceEventKind.CONTROLLER_OUTPUT,
            {
                "node_id": _Shared.NODE_ID,
                "output_spec": _Shared.make_io_spec(name="ctrl_output", digest="ghi789"),
            },
        ),
        (
            "batch_item",
            TraceEventKind.BATCH_ITEM,
            {
                "list_stuff_code": "list_digest_001",
                "item_stuff_code": "item_digest_001",
                "item_index": 0,
                "batch_controller_node_id": _Shared.PARENT_NODE_ID,
            },
        ),
        (
            "batch_aggregate",
            TraceEventKind.BATCH_AGGREGATE,
            {
                "output_list_stuff_code": "agg_digest_001",
                "item_stuff_code": "item_digest_002",
                "item_index": 1,
                "batch_controller_node_id": _Shared.PARENT_NODE_ID,
            },
        ),
        (
            "parallel_combine",
            TraceEventKind.PARALLEL_COMBINE,
            {
                "combined_stuff_code": "combined_001",
                "branch_stuff_codes": ["branch_a", "branch_b"],
                "parallel_controller_node_id": _Shared.PARENT_NODE_ID,
                "branch_producer_node_ids": [("branch_a", "graph_1:wf_a:node_0"), ("branch_b", "graph_1:wf_b:node_0")],
            },
        ),
        (
            "execution_data",
            TraceEventKind.EXECUTION_DATA,
            {
                "node_id": _Shared.NODE_ID,
                "execution_data": {"rendered_prompt": "hello", "resolved_model": "claude-sonnet"},
            },
        ),
        (
            "usage_report",
            TraceEventKind.USAGE_REPORT,
            {
                "node_id": _Shared.NODE_ID,
                "tokens_usage": _Shared.make_llm_tokens_usage(),
            },
        ),
    ]

    EVENT_CLASSES: ClassVar[dict[TraceEventKind, type[TraceEvent]]] = {
        TraceEventKind.PIPE_START: PipeStartEvent,
        TraceEventKind.PIPE_END_SUCCESS: PipeEndSuccessEvent,
        TraceEventKind.PIPE_END_ERROR: PipeEndErrorEvent,
        TraceEventKind.EDGE: EdgeEvent,
        TraceEventKind.CONTROLLER_OUTPUT: ControllerOutputEvent,
        TraceEventKind.BATCH_ITEM: BatchItemEvent,
        TraceEventKind.BATCH_AGGREGATE: BatchAggregateEvent,
        TraceEventKind.PARALLEL_COMBINE: ParallelCombineEvent,
        TraceEventKind.EXECUTION_DATA: ExecutionDataEvent,
        TraceEventKind.USAGE_REPORT: UsageReportEvent,
    }

    @pytest.mark.parametrize(
        ("event_kind", "extra_fields"),
        [(entry[1], entry[2]) for entry in EVENTS_AND_KINDS],
        ids=[entry[0] for entry in EVENTS_AND_KINDS],
    )
    def test_round_trip_per_event_type(self, event_kind: TraceEventKind, extra_fields: dict[str, Any]) -> None:
        """Each event type survives JSON serialization round-trip."""
        event_cls = self.EVENT_CLASSES[event_kind]
        event = event_cls(**_Shared.make_base_fields(), **extra_fields)

        json_str = event.model_dump_json()
        restored = event_cls.model_validate_json(json_str)

        assert restored == event
        assert restored.model_dump()["event_kind"] == event_kind

    @pytest.mark.parametrize(
        ("event_kind", "extra_fields"),
        [(entry[1], entry[2]) for entry in EVENTS_AND_KINDS],
        ids=[entry[0] for entry in EVENTS_AND_KINDS],
    )
    def test_discriminated_union_deserialization(self, event_kind: TraceEventKind, extra_fields: dict[str, Any]) -> None:
        """AnyTraceEvent discriminated union resolves to the correct subclass."""
        event_cls = self.EVENT_CLASSES[event_kind]
        event = event_cls(**_Shared.make_base_fields(), **extra_fields)

        json_str = event.model_dump_json()
        restored = _any_trace_event_adapter.validate_json(json_str)

        assert type(restored) is event_cls
        assert restored.model_dump()["event_kind"] == event_kind

    def test_pipe_start_with_empty_inputs(self) -> None:
        """PipeStartEvent works with no input specs."""
        event = PipeStartEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="noop_pipe",
            pipe_type="PipeNoop",
            node_kind=NodeKind.OPERATOR,
        )

        json_str = event.model_dump_json()
        restored = PipeStartEvent.model_validate_json(json_str)

        assert restored.input_specs == []
        assert restored.parent_node_id is None

    def test_pipe_end_success_with_no_output(self) -> None:
        """PipeEndSuccessEvent works with no output spec."""
        event = PipeEndSuccessEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            ended_at=_Shared.TIMESTAMP,
        )

        json_str = event.model_dump_json()
        restored = PipeEndSuccessEvent.model_validate_json(json_str)

        assert restored.output_spec is None
        assert restored.metrics == {}

    def test_io_spec_survives_round_trip_within_event(self) -> None:
        """IOSpec fields (digest, preview, concept) are preserved through event serialization."""
        io_spec = IOSpec(
            name="complex_stuff",
            concept="StructuredData",
            content_type="application/json",
            preview='{"key": "value"}',
            size=16,
            digest="sha256_abc",
            extra={"custom_field": "custom_value"},
        )
        event = PipeStartEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            input_specs=[io_spec],
        )

        json_str = event.model_dump_json()
        restored = PipeStartEvent.model_validate_json(json_str)

        restored_io = restored.input_specs[0]
        assert restored_io.name == "complex_stuff"
        assert restored_io.concept == "StructuredData"
        assert restored_io.digest == "sha256_abc"
        assert restored_io.extra == {"custom_field": "custom_value"}

    def test_error_spec_survives_round_trip_within_event(self) -> None:
        """ErrorSpec fields are preserved through event serialization."""
        error = ErrorSpec(
            error_type="ValidationError",
            message="Field 'name' is required",
            stack="long stack trace here...",
        )
        event = PipeEndErrorEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            ended_at=_Shared.TIMESTAMP,
            error=error,
        )

        json_str = event.model_dump_json()
        restored = PipeEndErrorEvent.model_validate_json(json_str)

        assert restored.error.error_type == "ValidationError"
        assert restored.error.message == "Field 'name' is required"
        assert restored.error.stack == "long stack trace here..."

    def test_usage_report_with_llm_tokens_round_trip(self) -> None:
        """UsageReportEvent with LLMTokensUsage survives round-trip via AnyTokensUsage discriminator."""
        tokens_usage = _Shared.make_llm_tokens_usage()
        event = UsageReportEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            tokens_usage=tokens_usage,
        )

        json_str = event.model_dump_json()
        restored = _any_trace_event_adapter.validate_json(json_str)

        assert isinstance(restored, UsageReportEvent)
        assert isinstance(restored.tokens_usage, LLMTokensUsage)
        assert restored.tokens_usage.inference_model_name == "claude-sonnet"
        assert restored.tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == 100
        assert restored.tokens_usage.nb_tokens_by_category[TokenCategory.OUTPUT] == 50

    def test_all_event_kinds_covered(self) -> None:
        """Every TraceEventKind has a corresponding test case and event class."""
        tested_kinds = {entry[1] for entry in self.EVENTS_AND_KINDS}
        all_kinds = set(TraceEventKind)
        assert tested_kinds == all_kinds, f"Missing test cases for: {all_kinds - tested_kinds}"

        mapped_kinds = set(self.EVENT_CLASSES.keys())
        assert mapped_kinds == all_kinds, f"Missing class mappings for: {all_kinds - mapped_kinds}"
