from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import ErrorSpec, GraphSpec, NodeKind, NodeStatus
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.trace_events import PipeEndErrorEvent, PipeEndSuccessEvent, PipeStartEvent, TraceEvent, UsageReportEvent

_GRAPH_ID = "run_7Qd2kV"
_T0 = datetime(2026, 10, 12, 9, 30, 0, tzinfo=UTC)
_RUN = "exec-run"
_ITEM = "exec-item-2"
_ENTRY_PATH = "filings.review_filings"
_BATCH_PATH = f"{_ENTRY_PATH}/step_3"
_ITEM_PATH = f"{_BATCH_PATH}/item_2"
_LEAF_PATH = f"{_ITEM_PATH}/step_2"
_ENTRY_NODE_ID = f"{_GRAPH_ID}:{_RUN}:node_0"
_BATCH_NODE_ID = f"{_GRAPH_ID}:{_RUN}:node_1"


class _Writer:
    """Writes the events of one attempt of one execution, numbering them as its tracer does."""

    def __init__(self, *, execution: str, attempt: int, lineage: list[ExecutionAttempt]) -> None:
        self.execution = execution
        self.attempt = attempt
        self.lineage = lineage
        self.sequence = 0

    def _base(self, *, path: str) -> dict[str, Any]:
        base: dict[str, Any] = {
            "pipeline_run_id": _GRAPH_ID,
            "workflow_id": self.execution,
            "attempt": self.attempt,
            "lineage": self.lineage,
            "path": path,
            "timestamp": _T0 + timedelta(seconds=self.attempt * 100 + self.sequence),
            "sequence": self.sequence,
            "mode": PipeRunMode.LIVE,
        }
        self.sequence += 1
        return base

    def start(self, *, node_id: str, parent_node_id: str | None, path: str, pipe_code: str, pipe_type: str) -> PipeStartEvent:
        node_kind = NodeKind.CONTROLLER if pipe_type in {"PipeSequence", "PipeBatch"} else NodeKind.OPERATOR
        return PipeStartEvent(
            **self._base(path=path),
            node_id=node_id,
            parent_node_id=parent_node_id,
            pipe_code=pipe_code,
            pipe_ref=f"filings.{pipe_code}",
            pipe_type=pipe_type,
            node_kind=node_kind,
        )

    def succeed(self, *, node_id: str, path: str, pipe_code: str, pipe_type: str) -> PipeEndSuccessEvent:
        base = self._base(path=path)
        return PipeEndSuccessEvent(
            **base, node_id=node_id, pipe_code=pipe_code, pipe_ref=f"filings.{pipe_code}", pipe_type=pipe_type, ended_at=base["timestamp"]
        )

    def fail(self, *, node_id: str, path: str, pipe_code: str, pipe_type: str) -> PipeEndErrorEvent:
        base = self._base(path=path)
        return PipeEndErrorEvent(
            **base,
            node_id=node_id,
            pipe_code=pipe_code,
            pipe_ref=f"filings.{pipe_code}",
            pipe_type=pipe_type,
            ended_at=base["timestamp"],
            error=ErrorSpec(error_type="WorkerLostError", message="An internal error occurred."),
        )

    def usage(self, *, node_id: str, path: str) -> UsageReportEvent:
        return UsageReportEvent(
            **self._base(path=path),
            node_id=node_id,
            tokens_usage=LLMTokensUsage(
                job_metadata=JobMetadata(
                    run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_test", pipeline_run_id=_GRAPH_ID),
                    pipe_code="condense_filing",
                    unit_job_id=UnitJobId.LLM_GEN_TEXT,
                    job_category=JobCategory.LLM_JOB,
                ),
                inference_model_name="test-model",
                inference_model_id="test-model-id",
                unit_costs={CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0},
                nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
            ),
        )


def _item_attempt_events(*, attempt: int, run_attempt: int, node_prefix: str, is_lost: bool) -> list[TraceEvent]:
    """One attempt of item 2's execution: the item's sequence, the step that condenses its filing, and that step's usage."""
    writer = _Writer(execution=_ITEM, attempt=attempt, lineage=[ExecutionAttempt(execution=_RUN, attempt=run_attempt)])
    item_node_id = f"{node_prefix}:node_0"
    leaf_node_id = f"{node_prefix}:node_1"
    events: list[TraceEvent] = [
        writer.start(node_id=item_node_id, parent_node_id=_BATCH_NODE_ID, path=_ITEM_PATH, pipe_code="summarize_filing", pipe_type="PipeSequence"),
        writer.start(node_id=leaf_node_id, parent_node_id=item_node_id, path=_LEAF_PATH, pipe_code="condense_filing", pipe_type="PipeLLM"),
        writer.usage(node_id=leaf_node_id, path=_ITEM_PATH),
    ]
    if is_lost:
        events.append(writer.fail(node_id=leaf_node_id, path=_LEAF_PATH, pipe_code="condense_filing", pipe_type="PipeLLM"))
        events.append(writer.fail(node_id=item_node_id, path=_ITEM_PATH, pipe_code="summarize_filing", pipe_type="PipeSequence"))
    else:
        events.append(writer.succeed(node_id=leaf_node_id, path=_LEAF_PATH, pipe_code="condense_filing", pipe_type="PipeLLM"))
        events.append(writer.succeed(node_id=item_node_id, path=_ITEM_PATH, pipe_code="summarize_filing", pipe_type="PipeSequence"))
    return events


def _run_attempt_events(*, attempt: int, is_ended: bool) -> list[TraceEvent]:
    """One attempt of the run's own execution: the entry sequence and its batch."""
    writer = _Writer(execution=_RUN, attempt=attempt, lineage=[])
    events: list[TraceEvent] = [
        writer.start(node_id=_ENTRY_NODE_ID, parent_node_id=None, path=_ENTRY_PATH, pipe_code="review_filings", pipe_type="PipeSequence"),
        writer.start(
            node_id=_BATCH_NODE_ID, parent_node_id=_ENTRY_NODE_ID, path=_BATCH_PATH, pipe_code="summarize_filing_batch", pipe_type="PipeBatch"
        ),
    ]
    if is_ended:
        events.append(writer.succeed(node_id=_BATCH_NODE_ID, path=_BATCH_PATH, pipe_code="summarize_filing_batch", pipe_type="PipeBatch"))
        events.append(writer.succeed(node_id=_ENTRY_NODE_ID, path=_ENTRY_PATH, pipe_code="review_filings", pipe_type="PipeSequence"))
    return events


def _nodes_by_path(graph_spec: GraphSpec) -> dict[str, list[NodeStatus]]:
    nodes_by_path: dict[str, list[NodeStatus]] = {}
    for node in graph_spec.nodes:
        assert node.path is not None
        nodes_by_path.setdefault(node.path, []).append(node.status)
    return nodes_by_path


class TestAssemblerSupersession:
    @pytest.mark.parametrize(
        "lost_node_prefix",
        [f"{_GRAPH_ID}:{_ITEM}", f"{_GRAPH_ID}:{_ITEM}-first-run"],
        ids=["attempts_share_node_ids", "attempts_mint_their_own_node_ids"],
    )
    def test_a_retried_item_shows_its_current_attempt_alone(self, lost_node_prefix: str) -> None:
        """Both attempts of the item name one invocation at each path; the graph keeps the later, with no phantom failure."""
        events = [
            *_run_attempt_events(attempt=1, is_ended=True),
            *_item_attempt_events(attempt=1, run_attempt=1, node_prefix=lost_node_prefix, is_lost=True),
            *_item_attempt_events(attempt=2, run_attempt=1, node_prefix=f"{_GRAPH_ID}:{_ITEM}", is_lost=False),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert _nodes_by_path(graph_spec) == {
            _ENTRY_PATH: [NodeStatus.SUCCEEDED],
            _BATCH_PATH: [NodeStatus.SUCCEEDED],
            _ITEM_PATH: [NodeStatus.SUCCEEDED],
            _LEAF_PATH: [NodeStatus.SUCCEEDED],
        }
        # The lost attempt's inference was spent all the same: the run's total counts it, as usage no node shown holds.
        assert graph_spec.usage is not None
        assert (graph_spec.usage.total.inference_calls, graph_spec.usage.unattributed.inference_calls) == (2, 1)
        leaf_node = next(node for node in graph_spec.nodes if node.path == _LEAF_PATH)
        assert leaf_node.usage is not None
        assert leaf_node.usage.inference_calls == 1

    def test_a_new_attempt_of_the_run_supersedes_every_item_the_earlier_one_dispatched(self) -> None:
        """Attempt 2 of the run's execution runs the batch again: the item attempt 1 dispatched is gone, though it ended well."""
        events = [
            *_run_attempt_events(attempt=1, is_ended=False),
            *_item_attempt_events(attempt=1, run_attempt=1, node_prefix=f"{_GRAPH_ID}:{_ITEM}-under-run-1", is_lost=False),
            *_run_attempt_events(attempt=2, is_ended=True),
            *_item_attempt_events(attempt=1, run_attempt=2, node_prefix=f"{_GRAPH_ID}:{_ITEM}", is_lost=False),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert _nodes_by_path(graph_spec) == {
            _ENTRY_PATH: [NodeStatus.SUCCEEDED],
            _BATCH_PATH: [NodeStatus.SUCCEEDED],
            _ITEM_PATH: [NodeStatus.SUCCEEDED],
            _LEAF_PATH: [NodeStatus.SUCCEEDED],
        }
        assert {node.node_id for node in graph_spec.nodes if node.path == _LEAF_PATH} == {f"{_GRAPH_ID}:{_ITEM}:node_1"}
        assert graph_spec.usage is not None
        assert (graph_spec.usage.total.inference_calls, graph_spec.usage.unattributed.inference_calls) == (2, 1)

    def test_a_superseded_attempt_does_not_date_the_graph(self) -> None:
        """The graph is dated by its earliest current event: the run's first attempt, lost an hour before the second
        started, is no part of the graph, so it does not date it either.
        """
        one_hour = timedelta(hours=1)
        second_attempt_events = [
            event.model_copy(update={"timestamp": event.timestamp + one_hour})
            for event in [
                *_run_attempt_events(attempt=2, is_ended=True),
                *_item_attempt_events(attempt=1, run_attempt=2, node_prefix=f"{_GRAPH_ID}:{_ITEM}", is_lost=False),
            ]
        ]
        first_attempt_events = [
            *_run_attempt_events(attempt=1, is_ended=False),
            *_item_attempt_events(attempt=1, run_attempt=1, node_prefix=f"{_GRAPH_ID}:{_ITEM}-under-run-1", is_lost=True),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=[*first_attempt_events, *second_attempt_events], graph_id=_GRAPH_ID)

        second_attempt_start = min(event.timestamp for event in second_attempt_events)
        assert second_attempt_start - max(event.timestamp for event in first_attempt_events) > one_hour - timedelta(minutes=5)
        assert graph_spec.created_at == second_attempt_start
