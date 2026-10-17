"""Serialization round-trip tests for trace event models."""

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import TypeAdapter, ValidationError
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.errors.problem import PipelexProblem, ProblemView, make_location, make_problem
from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping
from pipelex.graph.graphspec import EdgeKind, IOSpec, NodeKind
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing import trace_events as trace_events_module
from pipelex.tracing.trace_events import (
    AnyTraceEvent,
    BatchAggregateEvent,
    BatchFannedOutEvent,
    BatchItemEvent,
    ConditionOutputMergeEvent,
    ConditionResolvedEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ExecutionDataEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSkippedEvent,
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
    TIMESTAMP = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
    NODE_ID = "graph_1:wf_pipe_router_xyz:node_0"
    PARENT_NODE_ID = "graph_1:wf_pipe_router_xyz:node_1"
    PATH = "records.review_records/step_2/item_3"

    @staticmethod
    def make_base_fields(sequence: int = 0) -> dict[str, Any]:
        return {
            "pipeline_run_id": _Shared.PIPELINE_RUN_ID,
            "workflow_id": _Shared.WORKFLOW_ID,
            "attempt": 2,
            "lineage": [ExecutionAttempt(execution="wf_run", attempt=1)],
            "path": _Shared.PATH,
            "timestamp": _Shared.TIMESTAMP,
            "sequence": sequence,
            "mode": PipeRunMode.LIVE,
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
    def make_error_problem() -> PipelexProblem:
        return make_problem(
            code=CoreCode.PROVIDER_UNAVAILABLE,
            view=ProblemView.CALLER,
            location=make_location(pipe="gen_summary", path=["records", "gen_summary"]),
        )

    @staticmethod
    def make_job_metadata() -> JobMetadata:
        return JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_test", pipeline_run_id=_Shared.PIPELINE_RUN_ID),
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
                "pipe_ref": "records.gen_summary",
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
                "pipe_code": "gen_summary",
                "pipe_ref": "records.gen_summary",
                "pipe_type": "PipeLLM",
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
                "pipe_code": "gen_summary",
                "pipe_ref": "records.gen_summary",
                "pipe_type": "PipeLLM",
                "ended_at": _Shared.TIMESTAMP,
                "error": _Shared.make_error_problem(),
                "error_stack": "Traceback (most recent call last):\n  File ...",
            },
        ),
        (
            "pipe_end_skipped",
            TraceEventKind.PIPE_END_SKIPPED,
            {
                "node_id": _Shared.NODE_ID,
                "pipe_code": "gen_summary",
                "pipe_ref": "records.gen_summary",
                "pipe_type": "PipeLLM",
                "ended_at": _Shared.TIMESTAMP,
                "skip_reason": "skipped because input 'source' is absent",
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
            "condition_output_merge",
            TraceEventKind.CONDITION_OUTPUT_MERGE,
            {
                "merge": ConditionOutputMerge(
                    condition_node_id=_Shared.PARENT_NODE_ID,
                    shared_digest="shared_001",
                    merged_digests=["outcome_a"],
                    shared_typing=ConditionOutputTyping(concept="Anything", multiplicity=True),
                ),
            },
        ),
        (
            "batch_fanned_out",
            TraceEventKind.BATCH_FANNED_OUT,
            {
                "node_id": _Shared.NODE_ID,
                "item_count": 3,
                "branch_pipe_code": "summarize_record",
                "branch_pipe_ref": "records.summarize_record",
                "branch_pipe_type": "PipeLLM",
            },
        ),
        (
            "condition_resolved",
            TraceEventKind.CONDITION_RESOLVED,
            {
                "node_id": _Shared.NODE_ID,
                "rendered_value": "urgent",
                "selected_outcome": "urgent",
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
        TraceEventKind.PIPE_END_SKIPPED: PipeEndSkippedEvent,
        TraceEventKind.EDGE: EdgeEvent,
        TraceEventKind.CONTROLLER_OUTPUT: ControllerOutputEvent,
        TraceEventKind.BATCH_ITEM: BatchItemEvent,
        TraceEventKind.BATCH_AGGREGATE: BatchAggregateEvent,
        TraceEventKind.PARALLEL_COMBINE: ParallelCombineEvent,
        TraceEventKind.CONDITION_OUTPUT_MERGE: ConditionOutputMergeEvent,
        TraceEventKind.BATCH_FANNED_OUT: BatchFannedOutEvent,
        TraceEventKind.CONDITION_RESOLVED: ConditionResolvedEvent,
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
            pipe_ref=None,
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
            pipe_code="test_pipe",
            pipe_ref=None,
            pipe_type="PipeFunc",
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            ended_at=_Shared.TIMESTAMP,
        )

        json_str = event.model_dump_json()
        restored = PipeEndSuccessEvent.model_validate_json(json_str)

        assert restored.output_spec is None
        assert restored.metrics == {}

    def test_io_spec_survives_round_trip_within_event(self) -> None:
        """IOSpec fields (digest, preview, concept, multiplicity) are preserved through event serialization."""
        io_spec = IOSpec(
            name="complex_stuff",
            concept="StructuredData",
            content_type="application/json",
            preview='{"key": "value"}',
            size=16,
            digest="sha256_abc",
            multiplicity=True,
            extra={"custom_field": "custom_value"},
        )
        event = PipeStartEvent(
            pipe_ref=None,
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
        assert restored_io.multiplicity is True
        assert restored_io.extra == {"custom_field": "custom_value"}

    def test_problem_survives_round_trip_within_event(self) -> None:
        """The problem and the stack are preserved through event serialization, with no member written as null."""
        error = make_problem(
            code=CoreCode.INPUT_MISSING,
            view=ProblemView.CALLER,
            params={"input": "name"},
            location=make_location(pipe="test_pipe", path=["test_pipe"]),
        )
        event = PipeEndErrorEvent(
            pipe_code="test_pipe",
            pipe_ref=None,
            pipe_type="PipeFunc",
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            ended_at=_Shared.TIMESTAMP,
            error=error,
            error_stack="long stack trace here...",
        )

        json_str = event.model_dump_json()
        restored = PipeEndErrorEvent.model_validate_json(json_str)

        assert restored.error == error
        assert restored.error.code == CoreCode.INPUT_MISSING
        assert restored.error.detail == "The request does not give the input 'name', which the method requires."
        assert restored.error.location is not None
        assert restored.error.location.as_wire() == {"pipe": "test_pipe", "path": ["test_pipe"]}
        assert restored.error_stack == "long stack trace here..."
        # The event writes its problem as the wire does, with no member written as null.
        assert json.loads(json_str)["error"] == error.to_wire()

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

    def test_pipe_start_carries_description_and_domain_code(self) -> None:
        event = PipeStartEvent(
            pipe_ref=None,
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="gen_summary",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            description="Summarize the input document.",
            domain_code="summarization",
        )

        assert event.description == "Summarize the input document."
        assert event.domain_code == "summarization"

    def test_pipe_start_description_and_domain_code_default_to_none(self) -> None:
        event = PipeStartEvent(
            pipe_ref=None,
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="noop_pipe",
            pipe_type="PipeNoop",
            node_kind=NodeKind.OPERATOR,
        )

        assert event.description is None
        assert event.domain_code is None

    def test_pipe_start_description_and_domain_code_round_trip(self) -> None:
        event = PipeStartEvent(
            pipe_ref=None,
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="gen_summary",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            description="Summarize the input document.",
            domain_code="summarization",
        )

        json_str = event.model_dump_json()
        restored = PipeStartEvent.model_validate_json(json_str)

        assert restored.description == "Summarize the input document."
        assert restored.domain_code == "summarization"

    @pytest.mark.parametrize(
        ("step_count", "branch_count"),
        [(None, None), (3, None), (None, 2)],
        ids=["operator", "sequence", "parallel"],
    )
    def test_pipe_start_carries_step_and_branch_counts(self, step_count: int | None, branch_count: int | None) -> None:
        """A sequence states its authored step count and a parallel its branch count as they start; any other pipe states neither."""
        event = PipeStartEvent(
            pipe_ref=None,
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            pipe_code="controller",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
            step_count=step_count,
            branch_count=branch_count,
        )

        payload = event.model_dump(mode="json")
        restored = _any_trace_event_adapter.validate_json(event.model_dump_json())

        assert payload["step_count"] == step_count
        assert payload["branch_count"] == branch_count
        assert isinstance(restored, PipeStartEvent)
        assert restored.step_count == step_count
        assert restored.branch_count == branch_count

    def test_condition_resolved_default_outcome_reads_null(self) -> None:
        """A condition that took its default outcome states `selected_outcome` as null, with the value it rendered."""
        event = ConditionResolvedEvent(
            **_Shared.make_base_fields(),
            node_id=_Shared.NODE_ID,
            rendered_value="unmatched",
            selected_outcome=None,
        )

        payload = event.model_dump(mode="json")
        restored = _any_trace_event_adapter.validate_json(event.model_dump_json())

        assert payload["event_kind"] == "condition_resolved"
        assert payload["selected_outcome"] is None
        assert payload["rendered_value"] == "unmatched"
        assert restored == event

    def test_batch_fanned_out_refuses_a_negative_item_count(self) -> None:
        with pytest.raises(ValidationError):
            BatchFannedOutEvent(
                **_Shared.make_base_fields(),
                node_id=_Shared.NODE_ID,
                item_count=-1,
                branch_pipe_code="summarize_record",
                branch_pipe_ref="records.summarize_record",
                branch_pipe_type="PipeLLM",
            )

    @pytest.mark.parametrize("mode", [PipeRunMode.LIVE, PipeRunMode.DRY], ids=["live", "dry"])
    def test_every_event_states_its_mode(self, mode: PipeRunMode) -> None:
        """Every event kind serializes the run mode it was written in, and reads it back."""
        for _, event_kind, extra_fields in self.EVENTS_AND_KINDS:
            event_cls = self.EVENT_CLASSES[event_kind]
            event = event_cls(**{**_Shared.make_base_fields(), "mode": mode}, **extra_fields)

            payload = event.model_dump(mode="json")
            restored = _any_trace_event_adapter.validate_json(event.model_dump_json())

            assert payload["mode"] == mode, event_kind
            assert restored.mode == mode, event_kind

    def test_an_event_without_a_mode_is_refused(self) -> None:
        """The mode is required: a line written before it existed fails to load rather than reading as live."""
        base_fields = _Shared.make_base_fields()
        del base_fields["mode"]
        with pytest.raises(ValidationError):
            PipeStartEvent(
                pipe_ref=None,
                **base_fields,
                node_id=_Shared.NODE_ID,
                pipe_code="noop_pipe",
                pipe_type="PipeNoop",
                node_kind=NodeKind.OPERATOR,
            )

    def test_an_event_naming_no_execution_is_refused(self) -> None:
        """An empty `workflow_id` names no execution: the event is refused when it is read, never when its chain is."""
        base_fields: dict[str, Any] = {**_Shared.make_base_fields(), "workflow_id": ""}
        with pytest.raises(ValidationError, match="workflow_id"):
            PipeStartEvent(
                pipe_ref=None,
                **base_fields,
                node_id=_Shared.NODE_ID,
                pipe_code="noop_pipe",
                pipe_type="PipeNoop",
                node_kind=NodeKind.OPERATOR,
            )

    def test_an_event_computes_its_keys_once_and_a_copy_computes_them_again(self, mocker: MockerFixture) -> None:
        """Every read and every assembly reads an event's keys, so they are computed once; an event is frozen, and a copy
        made with an update reads its keys from its own fields.
        """
        chain_key_spy = mocker.spy(trace_events_module, "execution_chain_key")
        event = PipeStartEvent(
            pipe_ref=None,
            **_Shared.make_base_fields(sequence=4),
            node_id=_Shared.NODE_ID,
            pipe_code="noop_pipe",
            pipe_type="PipeNoop",
            node_kind=NodeKind.OPERATOR,
        )

        for _ in range(3):
            assert event.chain_key == f"wf_run@1/{_Shared.WORKFLOW_ID}@2"
            assert event.store_key == (f"wf_run@1/{_Shared.WORKFLOW_ID}@2", "primary", "PipeStartEvent", 4)
        assert chain_key_spy.call_count == 1

        with pytest.raises(ValidationError, match="frozen"):
            event.attempt = 3  # type: ignore[misc]  # the static read-only error is the runtime contract under test
        retried = event.model_copy(update={"attempt": 3})
        assert retried.chain == [ExecutionAttempt(execution="wf_run", attempt=1), ExecutionAttempt(execution=_Shared.WORKFLOW_ID, attempt=3)]
        assert retried.store_key == (f"wf_run@1/{_Shared.WORKFLOW_ID}@3", "primary", "PipeStartEvent", 4)
        # The keys are no field: they are neither serialized nor compared.
        assert "chain_key" not in event.model_dump()
        assert _any_trace_event_adapter.validate_json(event.model_dump_json()) == event

    def test_all_event_kinds_covered(self) -> None:
        """Every TraceEventKind has a corresponding test case and event class."""
        tested_kinds = {entry[1] for entry in self.EVENTS_AND_KINDS}
        all_kinds = set(TraceEventKind)
        assert tested_kinds == all_kinds, f"Missing test cases for: {all_kinds - tested_kinds}"

        mapped_kinds = set(self.EVENT_CLASSES.keys())
        assert mapped_kinds == all_kinds, f"Missing class mappings for: {all_kinds - mapped_kinds}"
