"""Unit tests for the graphspec_to_orchestration_mermaid function."""

from typing import Any

from pipelex.graph.graphspec import EdgeSpec, GraphSpec, NodeSpec, PipelineRef
from pipelex.graph.mermaid import graphspec_to_orchestration_mermaid
from pipelex.tools.misc.chart_utils import FlowchartDirection
from tests.unit.pipelex.graph.test_data import MermaidTestData


class TestGraphspecToMermaid:
    """Tests for the graphspec_to_mermaid function."""

    def _make_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> GraphSpec:
        """Helper to create a GraphSpec from test data."""
        return GraphSpec(
            graph_id=MermaidTestData.GRAPH_ID,
            created_at=MermaidTestData.CREATED_AT,
            pipeline_ref=PipelineRef(domain="test", main_pipe="test_pipe"),
            nodes=[NodeSpec(**node) for node in nodes],
            edges=[EdgeSpec(**edge) for edge in edges],
        )

    def test_basic_flowchart_header(self) -> None:
        """Test that output starts with correct flowchart header."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        assert result.startswith("flowchart TD")

    def test_custom_direction(self) -> None:
        """Test specifying a custom direction."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph, direction=FlowchartDirection.LEFT_TO_RIGHT)
        assert result.startswith("flowchart LR")

    def test_node_ids_are_sanitized(self) -> None:
        """Test that node IDs with special chars are sanitized."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        # Original ID has colons
        assert "run:123:step-2" not in result
        # Should have sanitized ID
        assert "n_" in result

    def test_node_label_uses_pipe_code(self) -> None:
        """Test that node labels use pipe_code."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        assert "generate_text" in result

    def test_controller_renders_as_subgraph(self) -> None:
        """Test that controllers with children render as subgraphs."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.CONTROLLER_NODE,
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[
                MermaidTestData.CONTAINS_EDGE_1,
                MermaidTestData.CONTAINS_EDGE_2,
            ],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        assert "subgraph" in result
        assert "main_sequence" in result
        assert "end" in result

    def test_data_edge_uses_dashed_arrow(self) -> None:
        """Test that DATA edges use dashed arrows."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[MermaidTestData.DATA_EDGE],
        )
        result = graphspec_to_orchestration_mermaid(graph, include_data_edges=True)
        assert "-.->" in result

    def test_data_edge_excluded_when_disabled(self) -> None:
        """Test that DATA edges are excluded when include_data_edges=False."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[MermaidTestData.DATA_EDGE],
        )
        result = graphspec_to_orchestration_mermaid(graph, include_data_edges=False)
        assert "-.->" not in result

    def test_control_edge_uses_solid_arrow(self) -> None:
        """Test that CONTROL edges use solid arrows."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[MermaidTestData.CONTROL_EDGE],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        # Should have solid arrow but not dashed
        assert " --> " in result
        assert "-.->" not in result

    def test_edge_label_renders_correctly(self) -> None:
        """Test that edge labels are rendered."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[MermaidTestData.DATA_EDGE],
        )
        result = graphspec_to_orchestration_mermaid(graph, include_data_edges=True)
        assert "generated_text" in result
        assert '|"' in result  # Label syntax

    def test_selected_outcome_edge_with_label(self) -> None:
        """Test that SELECTED_OUTCOME edges render with labels."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.CONTROLLER_NODE,
                MermaidTestData.FAILED_NODE,
            ],
            edges=[MermaidTestData.SELECTED_OUTCOME_EDGE],
        )
        result = graphspec_to_orchestration_mermaid(graph, include_selected_outcome_edges=True)
        assert "success_branch" in result

    def test_failed_node_has_failed_class(self) -> None:
        """Test that failed nodes get the :::failed class."""
        graph = self._make_graph(
            nodes=[MermaidTestData.FAILED_NODE],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        assert ":::failed" in result

    def test_input_node_uses_pill_shape(self) -> None:
        """Test that INPUT nodes use stadium/pill shape."""
        graph = self._make_graph(
            nodes=[MermaidTestData.INPUT_NODE],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        # Pill shape: ([...])
        assert '(["' in result

    def test_style_definitions_included(self) -> None:
        """Test that style definitions are included."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        result = graphspec_to_orchestration_mermaid(graph)
        assert "classDef failed" in result
        assert "classDef controller" in result

    def test_deterministic_output(self) -> None:
        """Test that output is deterministic (same input = same output)."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.CONTROLLER_NODE,
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
            ],
            edges=[
                MermaidTestData.CONTAINS_EDGE_1,
                MermaidTestData.CONTAINS_EDGE_2,
                MermaidTestData.DATA_EDGE,
            ],
        )
        result1 = graphspec_to_orchestration_mermaid(graph)
        result2 = graphspec_to_orchestration_mermaid(graph)
        assert result1 == result2

    def test_complex_graph_structure(self) -> None:
        """Test a complex graph with nested structure."""
        graph = self._make_graph(
            nodes=[
                MermaidTestData.CONTROLLER_NODE,
                MermaidTestData.OPERATOR_NODE_1,
                MermaidTestData.OPERATOR_NODE_2,
                MermaidTestData.FAILED_NODE,
            ],
            edges=[
                MermaidTestData.CONTAINS_EDGE_1,
                MermaidTestData.CONTAINS_EDGE_2,
                MermaidTestData.DATA_EDGE,
                MermaidTestData.CONTROL_EDGE,
            ],
        )
        result = graphspec_to_orchestration_mermaid(graph)

        # Verify structure
        assert "flowchart TD" in result
        assert "subgraph" in result
        assert "main_sequence" in result
        assert "generate_text" in result
        assert "compose_output" in result
        assert "end" in result
        # Failed node is not a child of controller, so rendered at top level
        assert "failed_pipe" in result
