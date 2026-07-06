"""Unit tests for the GraphAnalysis model."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pipelex.graph.graph_analysis import GraphAnalysis
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


class TestGraphAnalysis:
    """Tests for GraphAnalysis.from_graphspec() and helper methods."""

    GRAPH_ID: ClassVar[str] = "analysis_test:001"
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

    def test_nodes_by_id_lookup(self) -> None:
        """Test that nodes_by_id provides fast lookup by node_id."""
        nodes = [
            {"node_id": "node_1", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_a", "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_2", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_b", "status": NodeStatus.SUCCEEDED},
        ]
        graph = self._make_graph(nodes=nodes)
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "node_1" in analysis.nodes_by_id
        assert "node_2" in analysis.nodes_by_id
        assert analysis.nodes_by_id["node_1"].pipe_code == "pipe_a"
        assert analysis.nodes_by_id["node_2"].pipe_code == "pipe_b"

    def test_containment_tree_from_contains_edges(self) -> None:
        """Test that containment_tree is built from CONTAINS edges."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node_1 = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node_2 = {
            "node_id": "child_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_b",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge_1 = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        contains_edge_2 = {
            "edge_id": "edge_2",
            "source": "ctrl_1",
            "target": "child_2",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node_1, child_node_2],
            edges=[contains_edge_1, contains_edge_2],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "ctrl_1" in analysis.containment_tree
        assert set(analysis.containment_tree["ctrl_1"]) == {"child_1", "child_2"}

    def test_child_node_ids_populated(self) -> None:
        """Test that child_node_ids contains all CONTAINS edge targets."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "child_1" in analysis.child_node_ids
        assert "ctrl_1" not in analysis.child_node_ids

    def test_root_nodes_excludes_children(self) -> None:
        """Test that root_nodes contains only nodes not in any CONTAINS target."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        orphan_node = {
            "node_id": "orphan_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "standalone",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node, orphan_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        root_node_ids = {node.node_id for node in analysis.root_nodes}
        assert "ctrl_1" in root_node_ids
        assert "orphan_1" in root_node_ids
        assert "child_1" not in root_node_ids

    def test_controller_ids_are_parents(self) -> None:
        """Test that controller_node_ids contains all nodes with children."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        standalone_node = {
            "node_id": "standalone",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "independent",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node, standalone_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "ctrl_1" in analysis.controller_node_ids
        assert "child_1" not in analysis.controller_node_ids
        assert "standalone" not in analysis.controller_node_ids

    def test_stuff_registry_from_node_io_outputs(self) -> None:
        """Test that stuff_registry is populated from node outputs."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output_data", concept="Text", digest="digest_001", data="output content")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "digest_001" in analysis.stuff_registry
        stuff_info = analysis.stuff_registry["digest_001"]
        assert stuff_info.name == "output_data"
        assert stuff_info.concept == "Text"
        assert stuff_info.data == "output content"

    def test_stuff_registry_from_node_io_inputs(self) -> None:
        """Test that stuff_registry includes inputs without producers (pipeline inputs)."""
        consumer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="pipeline_input", concept="Text", digest="input_digest", data="input content")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[consumer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        assert "input_digest" in analysis.stuff_registry
        stuff_info = analysis.stuff_registry["input_digest"]
        assert stuff_info.name == "pipeline_input"
        assert stuff_info.data == "input content"

    def test_stuff_producers_map(self) -> None:
        """Test that stuff_producers maps digest to producer node_id."""
        producer_node = {
            "node_id": "producer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="digest_abc")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.stuff_producers.get("digest_abc") == "producer_1"

    def test_stuff_consumers_map(self) -> None:
        """Test that stuff_consumers maps digest to list of consumer node_ids."""
        producer_node = {
            "node_id": "producer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="shared_output", concept="Text", digest="shared_digest")],
            ),
        }
        consumer_a = {
            "node_id": "consumer_a",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer_a",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_a", concept="Text", digest="shared_digest")],
                outputs=[],
            ),
        }
        consumer_b = {
            "node_id": "consumer_b",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer_b",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input_b", concept="Text", digest="shared_digest")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_a, consumer_b])
        analysis = GraphAnalysis.from_graphspec(graph)

        consumers = analysis.stuff_consumers.get("shared_digest", [])
        assert set(consumers) == {"consumer_a", "consumer_b"}

    def test_controllers_excluded_from_stuff_tracking(self) -> None:
        """Test that controller nodes are excluded from stuff producer/consumer tracking."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="ctrl_input", concept="Text", digest="ctrl_digest")],
                outputs=[IOSpec(name="ctrl_output", concept="Text", digest="ctrl_out_digest")],
            ),
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="child_digest")],
            ),
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        # Controller should not be in producers
        assert analysis.stuff_producers.get("ctrl_out_digest") != "ctrl_1"
        # Child should be the producer
        assert analysis.stuff_producers.get("child_digest") == "child_1"

    def test_deterministic_analysis(self) -> None:
        """Test that same GraphSpec yields same analysis."""
        nodes = [
            {"node_id": "node_1", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_a", "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_2", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_b", "status": NodeStatus.SUCCEEDED},
        ]
        edges = [
            {"edge_id": "edge_1", "source": "node_1", "target": "node_2", "kind": EdgeKind.CONTROL},
        ]
        graph = self._make_graph(nodes=nodes, edges=edges)

        analysis1 = GraphAnalysis.from_graphspec(graph)
        analysis2 = GraphAnalysis.from_graphspec(graph)

        # Compare key fields
        assert analysis1.nodes_by_id.keys() == analysis2.nodes_by_id.keys()
        assert analysis1.containment_tree == analysis2.containment_tree
        assert analysis1.child_node_ids == analysis2.child_node_ids
        assert analysis1.controller_node_ids == analysis2.controller_node_ids
        assert [n.node_id for n in analysis1.root_nodes] == [n.node_id for n in analysis2.root_nodes]

    def test_get_children_helper(self) -> None:
        """Test the get_children helper method."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.get_children("ctrl_1") == ["child_1"]
        assert analysis.get_children("child_1") == []
        assert analysis.get_children("nonexistent") == []

    def test_is_controller_helper(self) -> None:
        """Test the is_controller helper method."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.is_controller("ctrl_1") is True
        assert analysis.is_controller("child_1") is False

    def test_is_root_helper(self) -> None:
        """Test the is_root helper method."""
        controller_node = {
            "node_id": "ctrl_1",
            "kind": NodeKind.CONTROLLER,
            "pipe_code": "main_sequence",
            "status": NodeStatus.SUCCEEDED,
        }
        child_node = {
            "node_id": "child_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_a",
            "status": NodeStatus.SUCCEEDED,
        }
        contains_edge = {
            "edge_id": "edge_1",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        graph = self._make_graph(
            nodes=[controller_node, child_node],
            edges=[contains_edge],
        )
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.is_root("ctrl_1") is True
        assert analysis.is_root("child_1") is False

    def test_get_stuff_info_helper(self) -> None:
        """Test the get_stuff_info helper method."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="digest_001", data="content")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        stuff_info = analysis.get_stuff_info("digest_001")
        assert stuff_info is not None
        assert stuff_info.name == "output"
        assert stuff_info.concept == "Text"
        assert stuff_info.data == "content"

        assert analysis.get_stuff_info("nonexistent") is None

    def test_get_producer_helper(self) -> None:
        """Test the get_producer helper method."""
        producer_node = {
            "node_id": "producer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="digest_001")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.get_producer("digest_001") == "producer_1"
        assert analysis.get_producer("nonexistent") is None

    def test_get_consumers_helper(self) -> None:
        """Test the get_consumers helper method."""
        producer_node = {
            "node_id": "producer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="digest_001")],
            ),
        }
        consumer_node = {
            "node_id": "consumer_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input", concept="Text", digest="digest_001")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_node])
        analysis = GraphAnalysis.from_graphspec(graph)

        assert analysis.get_consumers("digest_001") == ["consumer_1"]
        assert analysis.get_consumers("nonexistent") == []

    def test_has_data_flow_info_helper(self) -> None:
        """Test the has_data_flow_info helper method."""
        # Graph with data flow
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="digest_001")],
            ),
        }
        graph_with_data = self._make_graph(nodes=[producer_node])
        analysis_with_data = GraphAnalysis.from_graphspec(graph_with_data)
        assert analysis_with_data.has_data_flow_info() is True

        # Graph without data flow
        empty_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "empty_pipe",
            "status": NodeStatus.SUCCEEDED,
        }
        graph_without_data = self._make_graph(nodes=[empty_node])
        analysis_without_data = GraphAnalysis.from_graphspec(graph_without_data)
        assert analysis_without_data.has_data_flow_info() is False

    def test_nested_containment_hierarchy(self) -> None:
        """Test analysis with nested controllers (grandparent -> parent -> child)."""
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
        analysis = GraphAnalysis.from_graphspec(graph)

        # Verify hierarchy
        assert analysis.get_children("ctrl_outer") == ["ctrl_inner"]
        assert analysis.get_children("ctrl_inner") == ["leaf_1"]
        assert analysis.get_children("leaf_1") == []

        # Verify controller status
        assert analysis.is_controller("ctrl_outer") is True
        assert analysis.is_controller("ctrl_inner") is True
        assert analysis.is_controller("leaf_1") is False

        # Verify root status
        assert analysis.is_root("ctrl_outer") is True
        assert analysis.is_root("ctrl_inner") is False
        assert analysis.is_root("leaf_1") is False

        # Only outer_ctrl should be in root_nodes
        root_ids = {node.node_id for node in analysis.root_nodes}
        assert root_ids == {"ctrl_outer"}
