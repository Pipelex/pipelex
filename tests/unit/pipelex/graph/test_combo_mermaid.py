from datetime import datetime, timezone
from typing import Any, ClassVar

from pipelex.graph.graphspec import (
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
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory

from .conftest import make_graph_config


class TestMermaidflow:
    """Tests for MermaidflowFactory.make_from_graphspec function."""

    GRAPH_ID: ClassVar[str] = "mermaidflow_test:001"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

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
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)
        assert "No data flow information available" in result.mermaid_code

    def test_controller_renders_as_subgraph(self) -> None:
        """Test that controllers with children render as subgraphs."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "generate_text",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        contains_edge = {
            "edge_id": "edge_contains_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # Should have subgraph for controller
        assert "subgraph" in result.mermaid_code
        assert "main_sequence" in result.mermaid_code
        assert "end" in result.mermaid_code
        # Child node should be inside
        assert "generate_text" in result.mermaid_code

    def test_stuff_nodes_appear_with_producer(self) -> None:
        """Test that stuff nodes appear next to their producer pipes."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        producer_node = {
            "node_id": "prod_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer_pipe",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="my_output", concept="TextConcept", digest="stuff_abc123")],
            ),
        }
        contains_edge = {
            "edge_id": "edge_contains_1",
            "source": "ctrl_1",
            "target": "prod_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, producer_node],
            edges=[contains_edge],
        )
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # Stuff node should be rendered
        assert "my_output" in result.mermaid_code
        assert ":::stuff" in result.mermaid_code

    def test_pipeline_input_stuff_at_top_level(self) -> None:
        """Test that pipeline input stuffs (no producer) render at top level."""
        consumer_node = {
            "node_id": "consumer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer_pipe",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="pipeline_input", concept="Text", digest="input_digest_001")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[consumer_node])
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # Pipeline input stuff should appear
        assert "pipeline_input" in result.mermaid_code
        # Should have comment about no producer
        assert "Pipeline input stuff nodes" in result.mermaid_code or "no producer" in result.mermaid_code

    def test_data_flow_edges_producer_to_stuff_to_consumer(self) -> None:
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
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # Verify producer -> stuff -> consumer edges exist
        lines = result.mermaid_code.split("\n")
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
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # All pipe nodes and stuff should appear
        assert "producer" in result.mermaid_code
        assert "consumer_a" in result.mermaid_code
        assert "consumer_b" in result.mermaid_code

        # Multiple edges should exist
        lines = result.mermaid_code.split("\n")
        edge_lines = [line for line in lines if " --> " in line]
        # 1 edge producer->stuff, 2 edges stuff->consumers = 3 total
        assert len(edge_lines) >= 3

    def test_failed_node_has_failed_class(self) -> None:
        """Test that failed nodes get the :::failed class."""
        failed_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "failed_pipe",
            "status": NodeStatus.FAILED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        graph = self._make_graph(nodes=[failed_node])
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)
        assert ":::failed" in result.mermaid_code

    def test_style_definitions_included(self) -> None:
        """Test that style definitions are included."""
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
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)
        assert "classDef failed" in result.mermaid_code
        assert "classDef controller" in result.mermaid_code
        assert "classDef stuff" in result.mermaid_code

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
        graph_config = make_graph_config()

        # Without show_stuff_codes
        result_without = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config, show_stuff_codes=False)
        assert "xyzab" not in result_without.mermaid_code  # First 5 chars

        # With show_stuff_codes
        result_with = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config, show_stuff_codes=True)
        assert "xyzab" in result_with.mermaid_code  # First 5 chars should be shown

    def test_deterministic_output(self) -> None:
        """Test that output is deterministic (same input = same output)."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
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
        contains_edge_1 = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "node_1",
            "kind": EdgeKind.CONTAINS,
        }
        contains_edge_2 = {
            "edge_id": "edge_2",
            "source": "ctrl_1",
            "target": "node_2",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, producer_node, consumer_node],
            edges=[contains_edge_1, contains_edge_2],
        )
        graph_config = make_graph_config()
        result1 = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)
        result2 = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)
        assert result1.mermaid_code == result2.mermaid_code

    def test_subgraph_depth_coloring(self) -> None:
        """Test that nested subgraphs get depth-based coloring."""
        outer_ctrl = {
            "node_id": "ctrl_outer",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "outer_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        inner_ctrl = {
            "node_id": "ctrl_inner",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "inner_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        leaf_node = {
            "node_id": "leaf_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "leaf_pipe",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001")],
            ),
        }
        outer_contains = {
            "edge_id": "edge_1",
            "source": "ctrl_outer",
            "target": "ctrl_inner",
            "kind": EdgeKind.CONTAINS,
        }
        inner_contains = {
            "edge_id": "edge_2",
            "source": "ctrl_inner",
            "target": "leaf_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[outer_ctrl, inner_ctrl, leaf_node],
            edges=[outer_contains, inner_contains],
        )
        graph_config = make_graph_config()
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config=graph_config)

        # Should have multiple subgraphs with different colors
        assert "subgraph" in result.mermaid_code
        assert "style sg_" in result.mermaid_code  # Subgraph styling
