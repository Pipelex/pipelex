"""Test that NDJSON deduplication produces correct graphs when Temporal replays events.

Validates the end-to-end path: write duplicate events → read with dedup → assemble → correct GraphSpec.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipelex.graph.graphspec import EdgeKind, IOSpec, NodeKind, NodeStatus
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import (
    EdgeEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
)

_GRAPH_ID = "dedup_test"
_PIPELINE_RUN_ID = "dedup_run_001"
_WF_ID = "wf_replay"
_T0 = datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)


def _time_at(seconds: int) -> datetime:
    return _T0 + timedelta(seconds=seconds)


def _base(sequence: int) -> dict[str, Any]:
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": _WF_ID,
        "timestamp": _time_at(sequence),
        "sequence": sequence,
    }


def _make_sequence_events() -> list[TraceEvent]:
    """Create events for a simple sequence: parent + 2 children with DATA flow."""
    parent = f"{_GRAPH_ID}:{_WF_ID}:node_0"
    child_1 = f"{_GRAPH_ID}:{_WF_ID}:node_1"
    child_2 = f"{_GRAPH_ID}:{_WF_ID}:node_2"

    return [
        PipeStartEvent(
            **_base(0),
            node_id=parent,
            pipe_code="sequence",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
        ),
        PipeStartEvent(
            **_base(1),
            node_id=child_1,
            parent_node_id=parent,
            pipe_code="step_one",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
        ),
        EdgeEvent(
            **_base(2),
            edge_id=f"{_GRAPH_ID}:{_WF_ID}:edge_0",
            source_node_id=parent,
            target_node_id=child_1,
            edge_kind=EdgeKind.CONTAINS,
        ),
        PipeEndSuccessEvent(
            **_base(3),
            node_id=child_1,
            ended_at=_time_at(3),
            output_spec=IOSpec(name="output", digest="digest_a"),
        ),
        PipeStartEvent(
            **_base(4),
            node_id=child_2,
            parent_node_id=parent,
            pipe_code="step_two",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            input_specs=[IOSpec(name="input", digest="digest_a")],
        ),
        EdgeEvent(
            **_base(5),
            edge_id=f"{_GRAPH_ID}:{_WF_ID}:edge_1",
            source_node_id=parent,
            target_node_id=child_2,
            edge_kind=EdgeKind.CONTAINS,
        ),
        PipeEndSuccessEvent(
            **_base(6),
            node_id=child_2,
            ended_at=_time_at(6),
            output_spec=IOSpec(name="output", digest="digest_b"),
        ),
        PipeEndSuccessEvent(
            **_base(7),
            node_id=parent,
            ended_at=_time_at(7),
        ),
    ]


class TestNdjsonDedupAssembly:
    """Verify that duplicate events from Temporal replay are deduplicated and assemble correctly."""

    def test_duplicated_events_produce_correct_graph(self, tmp_path: Path) -> None:
        """Write every event twice (simulating Temporal replay), read, assemble — graph is correct."""
        events = _make_sequence_events()

        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        for event in events:
            event_log.emit(event)
            event_log.emit(event)  # Replay duplicate
        event_log.close()

        read_events = event_log.read_events(_PIPELINE_RUN_ID)
        assert len(read_events) == len(events), "Dedup should halve the event count"

        graph = GraphSpecAssembler.assemble(events=read_events, graph_id=_GRAPH_ID)

        assert len(graph.nodes) == 3
        for node in graph.nodes:
            assert node.status == NodeStatus.SUCCEEDED

        contains_edges = [edge for edge in graph.edges if edge.kind == EdgeKind.CONTAINS]
        data_edges = [edge for edge in graph.edges if edge.kind == EdgeKind.DATA]
        assert len(contains_edges) == 2
        assert len(data_edges) == 1

    def test_partial_replay_still_correct(self, tmp_path: Path) -> None:
        """Only some events are replayed — graph is still correct with no duplicates."""
        events = _make_sequence_events()

        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        for index_event, event in enumerate(events):
            event_log.emit(event)
            if index_event % 2 == 0:
                event_log.emit(event)  # Replay only even-indexed events
        event_log.close()

        read_events = event_log.read_events(_PIPELINE_RUN_ID)
        assert len(read_events) == len(events)

        graph = GraphSpecAssembler.assemble(events=read_events, graph_id=_GRAPH_ID)

        assert len(graph.nodes) == 3
        for node in graph.nodes:
            assert node.status == NodeStatus.SUCCEEDED

    @pytest.mark.parametrize("replay_count", [3, 5])
    def test_multiple_replays_still_correct(self, tmp_path: Path, replay_count: int) -> None:
        """Events replayed N times still assemble into a single correct graph."""
        events = _make_sequence_events()

        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        for _round in range(replay_count):
            for event in events:
                event_log.emit(event)
        event_log.close()

        read_events = event_log.read_events(_PIPELINE_RUN_ID)
        assert len(read_events) == len(events)

        graph = GraphSpecAssembler.assemble(events=read_events, graph_id=_GRAPH_ID)
        assert len(graph.nodes) == 3
