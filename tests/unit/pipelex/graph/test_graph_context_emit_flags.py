"""Unit tests for the GraphContext emit-stream flags (D4).

Pins that ``emit_graph_events`` / ``emit_usage_events`` default to True (backward-compatible
"context present means emit both") and that ``copy_for_child`` propagates whatever the parent
carried — so a costs-only or graph-only run keeps its gating as nested pipes spawn children.
"""

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext

DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)


class TestGraphContextEmitFlags:
    def test_defaults_emit_both_streams(self) -> None:
        """A GraphContext built without explicit flags emits both streams (legacy behavior)."""
        context = GraphContext(graph_id="run_1", data_inclusion=DATA_INCLUSION_OFF)
        assert context.emit_graph_events is True
        assert context.emit_usage_events is True

    def test_copy_for_child_preserves_costs_only_flags(self) -> None:
        """costs-only flags survive into a child context (graph off, costs on)."""
        parent = GraphContext(
            graph_id="run_1",
            data_inclusion=DATA_INCLUSION_OFF,
            emit_graph_events=False,
            emit_usage_events=True,
        )
        child = parent.copy_for_child(child_node_id="run_1:node_0", next_sequence=1)
        assert child.parent_node_id == "run_1:node_0"
        assert child.node_sequence == 1
        assert child.emit_graph_events is False
        assert child.emit_usage_events is True

    def test_copy_for_child_preserves_graph_only_flags(self) -> None:
        """graph-only flags survive into a child context (graph on, costs off)."""
        parent = GraphContext(
            graph_id="run_1",
            data_inclusion=DATA_INCLUSION_OFF,
            emit_graph_events=True,
            emit_usage_events=False,
        )
        child = parent.copy_for_child(child_node_id="run_1:node_0", next_sequence=2)
        assert child.emit_graph_events is True
        assert child.emit_usage_events is False
