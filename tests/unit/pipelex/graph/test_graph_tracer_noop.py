"""Unit tests for GraphTracerNoOp."""

from datetime import UTC, datetime, timedelta

from pipelex.graph.graph_tracer_protocol import GraphTracerNoOp
from pipelex.graph.graphspec import EdgeKind, NodeKind
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config, make_trace_context


class TestGraphTracerNoOp:
    """Tests for GraphTracerNoOp implementation."""

    def test_noop_returns_context(self) -> None:
        """Test that no-op tracer still returns valid context."""
        tracer = GraphTracerNoOp()
        context = tracer.setup(graph_id="noop-test", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.LIVE)

        assert context.graph_id == "noop-test"

    def test_noop_teardown_returns_none(self) -> None:
        """Test that no-op tracer returns None on teardown."""
        tracer = GraphTracerNoOp()
        tracer.setup(graph_id="noop-test", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.LIVE)
        result = tracer.teardown()

        assert result is None

    def test_noop_derives_no_path(self) -> None:
        """The no-op tracer records nothing, so it derives nothing that could fail the run, even from a context that
        could place no pipe.
        """
        unplaceable_context = make_trace_context().with_child_segment(segment="step_1")

        node_id, child_context = GraphTracerNoOp().on_pipe_start(
            pipe_ref="tests.step_one",
            trace_context=unplaceable_context,
            pipe_code="step_one",
            pipe_type="PipeCompose",
            node_kind=NodeKind.OPERATOR,
            started_at=datetime.now(UTC),
        )

        assert (child_context.parent_node_id, child_context.parent_path, child_context.child_segment) == (node_id, None, None)

    def test_noop_pipe_lifecycle(self) -> None:
        """Test that no-op tracer handles pipe lifecycle without errors."""
        tracer = GraphTracerNoOp()
        context = tracer.setup(graph_id="noop-test", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.LIVE)

        started_at = datetime.now(UTC)
        node_id, child_ctx = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        # Should return something usable even though it does nothing
        assert node_id is not None
        assert child_ctx is not None

        # These should not raise
        tracer.on_pipe_end_success(node_id=node_id, ended_at=started_at + timedelta(milliseconds=10))
        tracer.add_edge(
            source_node_id=node_id,
            target_node_id=node_id,
            edge_kind=EdgeKind.DATA,
        )
