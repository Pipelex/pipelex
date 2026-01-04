"""Unit tests for the graphspec_to_dataflow_mermaid function."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pipelex.graph.graphspec import EdgeSpec, GraphSpec, IOSpec, NodeIOSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.mermaid import graphspec_to_dataflow_mermaid


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

    def test_empty_io_shows_note(self) -> None:
        """Test that graph without IOSpec data shows informative note."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "some_pipe",
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
            "pipe_code": "producer",
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
            "pipe_code": "producer_pipe",
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
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output_data", concept="Text", digest="stuff_xyz")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
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
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="shared_data", concept="Text", digest="shared_001")],
            ),
        }
        consumer1_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer_a",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_a", concept="Text", digest="shared_001")],
                outputs=[],
            ),
        }
        consumer2_node = {
            "node_id": "node_3",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer_b",
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
            "pipe_code": "producer",
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
            "pipe_code": "failed_producer",
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
            "pipe_code": "producer",
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
            "pipe_code": "producer",
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
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
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
