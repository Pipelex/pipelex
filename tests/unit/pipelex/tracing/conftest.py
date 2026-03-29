"""Shared fixtures for tracing tests."""

from datetime import datetime, timezone

from pipelex.graph.graphspec import NodeKind
from pipelex.tracing.trace_events import PipeStartEvent


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
