"""Unit tests for the Mermaid exporter module."""

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from pipelex.observability.graphspec.graphspec import (
    EdgeKind,
    EdgeSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
)
from pipelex.observability.graphspec.mermaid import (
    escape_mermaid_label,
    graphspec_to_dataflow_mermaid,
    graphspec_to_orchestration_mermaid,
    sanitize_mermaid_id,
)


class MermaidTestData:
    """Test data for Mermaid exporter tests."""

    GRAPH_ID: ClassVar[str] = "test_run:123"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    # Node with special characters in ID
    CONTROLLER_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-1",
        "kind": NodeKind.CONTROLLER,
        "pipe_name": "main_sequence",
        "pipe_type": "PipeSequence",
        "status": NodeStatus.SUCCEEDED,
    }

    OPERATOR_NODE_1: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-2",
        "kind": NodeKind.OPERATOR,
        "pipe_name": "generate_text",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.SUCCEEDED,
    }

    OPERATOR_NODE_2: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-3",
        "kind": NodeKind.OPERATOR,
        "pipe_name": "compose_output",
        "pipe_type": "PipeCompose",
        "status": NodeStatus.SUCCEEDED,
    }

    FAILED_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-4",
        "kind": NodeKind.OPERATOR,
        "pipe_name": "failed_pipe",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.FAILED,
    }

    INPUT_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:input-1",
        "kind": NodeKind.INPUT,
        "pipe_name": "topic_input",
        "pipe_type": None,
        "status": NodeStatus.SUCCEEDED,
    }

    # Edges
    CONTAINS_EDGE_1: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_contains_1",
        "source": "run:123:step-1",
        "target": "run:123:step-2",
        "kind": EdgeKind.CONTAINS,
        "label": None,
    }

    CONTAINS_EDGE_2: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_contains_2",
        "source": "run:123:step-1",
        "target": "run:123:step-3",
        "kind": EdgeKind.CONTAINS,
        "label": None,
    }

    DATA_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_data_1",
        "source": "run:123:step-2",
        "target": "run:123:step-3",
        "kind": EdgeKind.DATA,
        "label": "generated_text",
    }

    CONTROL_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_control_1",
        "source": "run:123:step-2",
        "target": "run:123:step-3",
        "kind": EdgeKind.CONTROL,
        "label": None,
    }

    SELECTED_OUTCOME_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_outcome_1",
        "source": "run:123:step-1",
        "target": "run:123:step-4",
        "kind": EdgeKind.SELECTED_OUTCOME,
        "label": "success_branch",
    }


class TestSanitizeMermaidId:
    """Tests for the sanitize_mermaid_id function."""

    def test_sanitize_simple_id(self) -> None:
        """Test sanitizing a simple ID."""
        result = sanitize_mermaid_id("node_001")
        assert result.startswith("n_")
        assert len(result) == 12  # "n_" + 10 hex chars

    def test_sanitize_id_with_colons(self) -> None:
        """Test sanitizing an ID with colons."""
        result = sanitize_mermaid_id("run:123:step-1")
        assert result.startswith("n_")
        assert ":" not in result
        assert "-" not in result or result.startswith("n_")

    def test_sanitize_deterministic(self) -> None:
        """Test that sanitization is deterministic."""
        node_id = "run:abc:node-5"
        result1 = sanitize_mermaid_id(node_id)
        result2 = sanitize_mermaid_id(node_id)
        assert result1 == result2

    def test_sanitize_different_ids_produce_different_outputs(self) -> None:
        """Test that different IDs produce different sanitized outputs."""
        result1 = sanitize_mermaid_id("node_a")
        result2 = sanitize_mermaid_id("node_b")
        assert result1 != result2


class TestEscapeMermaidLabel:
    """Tests for the escape_mermaid_label function."""

    def test_escape_quotes(self) -> None:
        """Test escaping double quotes."""
        result = escape_mermaid_label('Label with "quotes"')
        assert '"' not in result
        assert "'" in result

    def test_escape_brackets(self) -> None:
        """Test escaping square brackets."""
        result = escape_mermaid_label("Label [with] brackets")
        assert "[" not in result
        assert "]" not in result
        assert "(" in result
        assert ")" in result

    def test_no_escape_needed(self) -> None:
        """Test label that doesn't need escaping."""
        result = escape_mermaid_label("simple_label")
        assert result == "simple_label"


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
        result = graphspec_to_orchestration_mermaid(graph, direction="LR")
        assert result.startswith("flowchart LR")

    def test_invalid_direction_raises(self) -> None:
        """Test that invalid direction raises ValueError."""
        graph = self._make_graph(
            nodes=[MermaidTestData.OPERATOR_NODE_1],
            edges=[],
        )
        with pytest.raises(ValueError, match="Invalid direction"):
            graphspec_to_orchestration_mermaid(graph, direction="INVALID")

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

    def test_node_label_uses_pipe_name(self) -> None:
        """Test that node labels use pipe_name."""
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


class TestDataFlowMermaid:
    """Tests for graphspec_to_dataflow_mermaid function."""

    GRAPH_ID: ClassVar[str] = "dataflow_test:001"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def _make_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
    ) -> GraphSpec:
        """Helper to create a GraphSpec with nodes and edges."""
        node_specs: list[NodeSpec] = []
        for node_dict in nodes:
            node_specs.append(NodeSpec(**node_dict))

        edge_specs: list[EdgeSpec] = []
        if edges:
            for edge_dict in edges:
                edge_specs.append(EdgeSpec(**edge_dict))

        return GraphSpec(
            graph_id=self.GRAPH_ID,
            created_at=self.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=node_specs,
            edges=edge_specs,
        )

    def test_default_direction_is_lr(self) -> None:
        """Test that data flow diagram defaults to LR direction."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input", concept="Text", digest="stuff_001")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_node])
        result = graphspec_to_dataflow_mermaid(graph)
        assert "flowchart LR" in result

    def test_invalid_direction_raises_error(self) -> None:
        """Test that invalid direction raises ValueError."""
        graph = self._make_graph(nodes=[])
        with pytest.raises(ValueError, match="Invalid direction"):
            graphspec_to_dataflow_mermaid(graph, direction="XX")

    def test_empty_io_shows_note(self) -> None:
        """Test that graph without IOSpec data shows informative note."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "some_pipe",
            "status": NodeStatus.SUCCEEDED,
        }
        graph = self._make_graph(nodes=[node])
        result = graphspec_to_dataflow_mermaid(graph)
        assert "No data flow information available" in result

    def test_stuff_nodes_rendered_as_pills(self) -> None:
        """Test that stuff nodes are rendered as stadium/pill shapes."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="my_stuff", concept="TextConcept", digest="abc123")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_dataflow_mermaid(graph)
        # Stuff nodes use pill shape: ([...])
        assert '(["my_stuff' in result
        assert ":::stuff" in result

    def test_pipe_nodes_rendered_as_rectangles(self) -> None:
        """Test that pipe nodes are rendered as rectangles."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer_pipe",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_dataflow_mermaid(graph)
        # Pipes use rectangle shape: [...]
        assert '["producer_pipe"]' in result
        assert ":::pipe" in result

    def test_edges_from_producer_to_stuff_to_consumer(self) -> None:
        """Test that edges connect producer -> stuff -> consumer."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output_data", concept="Text", digest="stuff_xyz")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_data", concept="Text", digest="stuff_xyz")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_node])
        result = graphspec_to_dataflow_mermaid(graph)

        # Verify producer -> stuff -> consumer edges
        lines = result.split("\n")
        edge_lines = [line for line in lines if " --> " in line]
        # Should have at least 2 edges: producer->stuff, stuff->consumer
        assert len(edge_lines) >= 2

    def test_multiple_consumers_of_same_stuff(self) -> None:
        """Test that multiple consumers of the same stuff are all connected."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="shared_data", concept="Text", digest="shared_001")],
            ),
        }
        consumer1_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "consumer_a",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_a", concept="Text", digest="shared_001")],
                outputs=[],
            ),
        }
        consumer2_node = {
            "node_id": "node_3",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "consumer_b",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_b", concept="Text", digest="shared_001")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer1_node, consumer2_node])
        result = graphspec_to_dataflow_mermaid(graph)

        # All three pipe nodes should appear
        assert "producer" in result
        assert "consumer_a" in result
        assert "consumer_b" in result

        # Edge lines from stuff to both consumers
        lines = result.split("\n")
        edge_lines = [line for line in lines if " --> " in line]
        # 1 edge producer->stuff, 2 edges stuff->consumers = 3 total
        assert len(edge_lines) >= 3

    def test_show_stuff_codes_option(self) -> None:
        """Test that show_stuff_codes option includes digest in label."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="xyzabc")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])

        # Without show_stuff_codes
        result_without = graphspec_to_dataflow_mermaid(graph, show_stuff_codes=False)
        assert "xyzab" not in result_without  # First 5 chars

        # With show_stuff_codes
        result_with = graphspec_to_dataflow_mermaid(graph, show_stuff_codes=True)
        assert "xyzab" in result_with  # First 5 chars should be shown

    def test_failed_pipe_has_failed_class(self) -> None:
        """Test that failed pipe nodes get the pipe_failed class."""
        failed_producer = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "failed_producer",
            "status": NodeStatus.FAILED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        graph = self._make_graph(nodes=[failed_producer])
        result = graphspec_to_dataflow_mermaid(graph)
        assert ":::pipe_failed" in result

    def test_style_definitions_included(self) -> None:
        """Test that style definitions for pipe and stuff classes are included."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_dataflow_mermaid(graph)
        assert "classDef pipe" in result
        assert "classDef pipe_failed" in result
        assert "classDef stuff" in result

    def test_concept_in_stuff_label(self) -> None:
        """Test that concept is included in stuff node label."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="my_output", concept="MyConcept", digest="stuff_001")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_dataflow_mermaid(graph)
        # Concept should be on a new line in the label
        assert "MyConcept" in result

    def test_deterministic_output(self) -> None:
        """Test that output is deterministic (same input = same output)."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_name": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input", concept="Text", digest="stuff_001")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_node])
        result1 = graphspec_to_dataflow_mermaid(graph)
        result2 = graphspec_to_dataflow_mermaid(graph)
        assert result1 == result2
