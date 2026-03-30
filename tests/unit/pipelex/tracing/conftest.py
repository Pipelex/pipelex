"""Shared fixtures for tracing tests."""

from datetime import datetime, timezone

from pipelex.graph.graphspec import EdgeKind, NodeKind
from pipelex.tracing.trace_events import EdgeEvent, PipeStartEvent


def make_trace_event(
    workflow_id: str = "wf_abc",
    sequence: int = 0,
    pipeline_run_id: str = "run_001",
) -> PipeStartEvent:
    """Create a minimal PipeStartEvent for testing."""
    return PipeStartEvent(
        pipeline_run_id=pipeline_run_id,
        workflow_id=workflow_id,
        timestamp=datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
        sequence=sequence,
        node_id=f"graph_1:{workflow_id}:node_{sequence}",
        pipe_code="test_pipe",
        pipe_type="PipeLLMGenText",
        node_kind=NodeKind.OPERATOR,
    )


def make_edge_event(
    workflow_id: str = "wf_abc",
    sequence: int = 0,
    pipeline_run_id: str = "run_001",
) -> EdgeEvent:
    """Create a minimal EdgeEvent for testing."""
    return EdgeEvent(
        pipeline_run_id=pipeline_run_id,
        workflow_id=workflow_id,
        timestamp=datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
        sequence=sequence,
        edge_id=f"graph_1:{workflow_id}:edge_{sequence}",
        source_node_id=f"graph_1:{workflow_id}:node_0",
        target_node_id=f"graph_1:{workflow_id}:node_1",
        edge_kind=EdgeKind.CONTAINS,
    )
