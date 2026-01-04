"""Unit tests for GraphContext."""

from pipelex.graph.graph_context import GraphContext


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
