"""Unit tests for GraphTracer."""

from datetime import UTC, datetime, timedelta

from pipelex.observability.graphspec import (
    EdgeKind,
    GraphContext,
    GraphTracer,
    GraphTracerNoOp,
    NodeKind,
    NodeStatus,
)


class TestGraphTracer:
    """Tests for GraphTracer implementation."""

    def test_setup_returns_initial_context(self) -> None:
        """Test that setup returns a properly initialized GraphContext."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="test-graph-001")

        assert context.graph_id == "test-graph-001"
        assert context.parent_node_id is None
        assert context.node_sequence == 0

    def test_setup_with_pipeline_ref(self) -> None:
        """Test that setup accepts pipeline reference parameters."""
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id="test-graph-002",
            pipeline_ref_domain="test.domain",
            pipeline_ref_main_pipe="main_pipe",
        )

        assert context.graph_id == "test-graph-002"
        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert graph_spec.pipeline_ref.domain == "test.domain"
        assert graph_spec.pipeline_ref.main_pipe == "main_pipe"

    def test_teardown_without_setup_returns_none(self) -> None:
        """Test that teardown returns None if not active."""
        tracer = GraphTracer()
        result = tracer.teardown()

        assert result is None

    def test_full_lifecycle_single_node(self) -> None:
        """Test tracking a single pipe execution."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="lifecycle-test")

        started_at = datetime.now(UTC)
        node_id, child_context = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        assert node_id == "lifecycle-test:node_0"
        assert child_context.parent_node_id == node_id

        ended_at = started_at + timedelta(milliseconds=100)
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            metrics={"tokens": 150.0},
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 1
        assert len(graph_spec.edges) == 0

        node = graph_spec.nodes[0]
        assert node.node_id == "lifecycle-test:node_0"
        assert node.pipe_name == "test_pipe"
        assert node.pipe_type == "PipeLLM"
        assert node.kind == NodeKind.OPERATOR
        assert node.status == NodeStatus.SUCCEEDED
        assert node.timing is not None
        assert node.timing.started_at == started_at
        assert node.timing.ended_at == ended_at
        assert node.timing.duration_ms == 100
        assert node.metrics == {"tokens": 150.0}

    def test_nested_pipe_execution(self) -> None:
        """Test tracking nested pipe execution with containment edges."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="nested-test")

        # Start parent (sequence controller)
        started_at = datetime.now(UTC)
        parent_id, parent_child_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_sequence",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        # Start child 1 (operator)
        child1_id, _child1_ctx = tracer.on_pipe_start(
            graph_context=parent_child_ctx,
            pipe_code="llm_step_1",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )

        tracer.on_pipe_end_success(
            node_id=child1_id,
            ended_at=started_at + timedelta(milliseconds=50),
        )

        # Start child 2 (operator)
        child2_id, _child2_ctx = tracer.on_pipe_start(
            graph_context=parent_child_ctx,
            pipe_code="llm_step_2",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=60),
        )

        tracer.on_pipe_end_success(
            node_id=child2_id,
            ended_at=started_at + timedelta(milliseconds=100),
        )

        # End parent
        tracer.on_pipe_end_success(
            node_id=parent_id,
            ended_at=started_at + timedelta(milliseconds=110),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 3
        assert len(graph_spec.edges) == 2  # parent -> child1, parent -> child2

        # Check containment edges
        edges = graph_spec.edges
        assert all(edge.kind == EdgeKind.CONTAINS for edge in edges)
        assert {edge.source for edge in edges} == {parent_id}
        assert {edge.target for edge in edges} == {child1_id, child2_id}

    def test_error_tracking(self) -> None:
        """Test tracking failed pipe execution."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="error-test")

        started_at = datetime.now(UTC)
        node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="failing_pipe",
            pipe_type="PipeFunc",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        tracer.on_pipe_end_error(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=50),
            error_type="ValueError",
            error_message="Something went wrong",
            error_stack="Traceback...",
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert node.status == NodeStatus.FAILED
        assert node.error is not None
        assert node.error.error_type == "ValueError"
        assert node.error.message == "Something went wrong"
        assert node.error.stack == "Traceback..."

    def test_running_nodes_marked_canceled_on_teardown(self) -> None:
        """Test that running nodes are marked as canceled on teardown."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="cancel-test")

        started_at = datetime.now(UTC)
        _node_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="stuck_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        # Don't call on_pipe_end_* - node stays running
        graph_spec = tracer.teardown()

        assert graph_spec is not None
        node = graph_spec.nodes[0]
        assert node.status == NodeStatus.CANCELED
        assert node.timing is not None
        assert node.timing.ended_at is not None

    def test_custom_edges(self) -> None:
        """Test adding custom edges between nodes."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="edge-test")

        started_at = datetime.now(UTC)
        node1_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="pipe_1",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(node_id=node1_id, ended_at=started_at + timedelta(milliseconds=10))

        node2_id, _ = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="pipe_2",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=20),
        )
        tracer.on_pipe_end_success(node_id=node2_id, ended_at=started_at + timedelta(milliseconds=30))

        # Add data flow edge
        tracer.add_edge(
            source_node_id=node1_id,
            target_node_id=node2_id,
            edge_kind=EdgeKind.DATA,
            label="output_text",
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.edges) == 1
        edge = graph_spec.edges[0]
        assert edge.source == node1_id
        assert edge.target == node2_id
        assert edge.kind == EdgeKind.DATA
        assert edge.label == "output_text"

    def test_selected_outcome_edge(self) -> None:
        """Test adding selected outcome edge for conditions."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="condition-test")

        started_at = datetime.now(UTC)
        condition_id, cond_ctx = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="my_condition",
            pipe_type="PipeCondition",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        outcome_id, _ = tracer.on_pipe_start(
            graph_context=cond_ctx,
            pipe_code="outcome_true",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )
        tracer.on_pipe_end_success(node_id=outcome_id, ended_at=started_at + timedelta(milliseconds=20))

        # Mark the selected outcome
        tracer.add_selected_outcome_edge(
            condition_node_id=condition_id,
            outcome_node_id=outcome_id,
            outcome_value="true",
        )

        tracer.on_pipe_end_success(node_id=condition_id, ended_at=started_at + timedelta(milliseconds=25))

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        selected_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.SELECTED_OUTCOME]
        assert len(selected_edges) == 1
        assert selected_edges[0].label == "true"


class TestGraphTracerNoOp:
    """Tests for GraphTracerNoOp implementation."""

    def test_noop_returns_context(self) -> None:
        """Test that no-op tracer still returns valid context."""
        tracer = GraphTracerNoOp()
        context = tracer.setup(graph_id="noop-test")

        assert context.graph_id == "noop-test"

    def test_noop_teardown_returns_none(self) -> None:
        """Test that no-op tracer returns None on teardown."""
        tracer = GraphTracerNoOp()
        tracer.setup(graph_id="noop-test")
        result = tracer.teardown()

        assert result is None

    def test_noop_pipe_lifecycle(self) -> None:
        """Test that no-op tracer handles pipe lifecycle without errors."""
        tracer = GraphTracerNoOp()
        context = tracer.setup(graph_id="noop-test")

        started_at = datetime.now(UTC)
        node_id, child_ctx = tracer.on_pipe_start(
            graph_context=context,
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


class TestGraphContext:
    """Tests for GraphContext model."""

    def test_make_node_id(self) -> None:
        """Test node ID generation."""
        context = GraphContext(graph_id="ctx-test", node_sequence=5)
        node_id = context.make_node_id()

        assert node_id == "ctx-test:node_5"

    def test_copy_for_child(self) -> None:
        """Test creating child context."""
        parent = GraphContext(graph_id="ctx-test", parent_node_id=None, node_sequence=0)
        child = parent.copy_for_child(child_node_id="ctx-test:node_0", next_sequence=1)

        assert child.graph_id == "ctx-test"
        assert child.parent_node_id == "ctx-test:node_0"
        assert child.node_sequence == 1
        # Parent should be unchanged
        assert parent.parent_node_id is None
        assert parent.node_sequence == 0
