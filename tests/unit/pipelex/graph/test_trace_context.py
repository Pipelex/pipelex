"""Unit tests for TraceContext."""

from tests.unit.pipelex.graph.conftest import make_trace_context


class TestTraceContext:
    """Tests for TraceContext model."""

    def test_make_node_id(self) -> None:
        """Test node ID generation."""
        context = make_trace_context(graph_id="ctx-test", node_sequence=5)
        node_id = context.make_node_id()

        assert node_id == "ctx-test:node_5"

    def test_copy_for_child(self) -> None:
        """Test creating child context."""
        parent = make_trace_context(graph_id="ctx-test", parent_node_id=None, node_sequence=0)
        child = parent.copy_for_child(child_node_id="ctx-test:node_0", next_sequence=1)

        assert child.graph_id == "ctx-test"
        assert child.parent_node_id == "ctx-test:node_0"
        assert child.node_sequence == 1
        # Parent should be unchanged
        assert parent.parent_node_id is None
        assert parent.node_sequence == 0

    def test_copy_for_child_preserves_data_inclusion(self) -> None:
        """Test that copy_for_child preserves data_inclusion config."""
        parent = make_trace_context(
            graph_id="ctx-test",
            stuff_json_content=True,
            stuff_text_content=True,
            stuff_html_content=True,
        )
        child = parent.copy_for_child(child_node_id="ctx-test:node_0", next_sequence=1)

        assert child.data_inclusion.stuff_json_content is True
        assert child.data_inclusion.stuff_text_content is True
        assert child.data_inclusion.stuff_html_content is True
