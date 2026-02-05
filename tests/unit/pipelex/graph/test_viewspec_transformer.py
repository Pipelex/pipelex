"""Unit tests for the ViewSpec transformer."""

from datetime import datetime, timezone
from typing import Any, ClassVar

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
    TimingSpec,
)
from pipelex.graph.reactflow.viewspec import LayoutSpec
from pipelex.graph.reactflow.viewspec_transformer import graphspec_to_viewspec
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.package_utils import get_package_version


class TestViewSpecTransformer:
    """Tests for graphspec_to_viewspec function."""

    GRAPH_ID: ClassVar[str] = "transformer_test:001"
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

    def test_minimal_graph_to_viewspec(self) -> None:
        """Test transforming a minimal graph to ViewSpec."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "test_pipe",
            "status": NodeStatus.SUCCEEDED,
        }
        graph = self._make_graph(nodes=[node])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        assert viewspec.graph_id == self.GRAPH_ID
        assert viewspec.engine == "reactflow"
        assert len(viewspec.nodes) == 1
        assert viewspec.nodes[0].id == "node_1"
        assert viewspec.nodes[0].label == "test_pipe"
        assert viewspec.nodes[0].kind == NodeKind.OPERATOR
        assert viewspec.nodes[0].status == NodeStatus.SUCCEEDED
        assert viewspec.nodes[0].type == "operator"
        assert len(viewspec.edges) == 0

    def test_node_kind_mapping(self) -> None:
        """Test that NodeKind is correctly mapped to ViewNode.type."""
        nodes = [
            {"node_id": "op_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
            {"node_id": "ctrl_1", "kind": NodeKind.CONTROLLER, "status": NodeStatus.SUCCEEDED},
            {"node_id": "input_1", "kind": NodeKind.INPUT, "status": NodeStatus.SUCCEEDED},
            {"node_id": "output_1", "kind": NodeKind.OUTPUT, "status": NodeStatus.SUCCEEDED},
            {"node_id": "artifact_1", "kind": NodeKind.ARTIFACT, "status": NodeStatus.SUCCEEDED},
            {"node_id": "error_1", "kind": NodeKind.ERROR, "status": NodeStatus.FAILED},
        ]
        graph = self._make_graph(nodes=nodes)
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        type_map = {node.id: node.type for node in viewspec.nodes}
        assert type_map["op_1"] == "operator"
        assert type_map["ctrl_1"] == "controller"
        assert type_map["input_1"] == "io"
        assert type_map["output_1"] == "io"
        assert type_map["artifact_1"] == "artifact"
        assert type_map["error_1"] == "error"

    def test_edge_kind_mapping(self) -> None:
        """Test that EdgeKind is correctly mapped to ViewEdge.type."""
        nodes = [
            {"node_id": "node_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_2", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_3", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
        ]
        edges = [
            {"edge_id": "edge_1", "source": "node_1", "target": "node_2", "kind": EdgeKind.CONTROL},
            {"edge_id": "edge_2", "source": "node_2", "target": "node_3", "kind": EdgeKind.DATA},
        ]
        graph = self._make_graph(nodes=nodes, edges=edges)
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        type_map = {edge.id: edge.type for edge in viewspec.edges}
        assert type_map["edge_1"] == "control"
        assert type_map["edge_2"] == "data"

        # DATA edges should be animated
        data_edge = next(edge for edge in viewspec.edges if edge.id == "edge_2")
        assert data_edge.animated is True

    def test_containment_tree_parent_id(self) -> None:
        """Test that parent_id is set correctly from containment tree."""
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
        graph = self._make_graph(nodes=[controller_node, child_node], edges=[contains_edge])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        child_view_node = next(node for node in viewspec.nodes if node.id == "child_1")
        assert child_view_node.parent_id == "ctrl_1"
        assert child_view_node.extent == "parent"

        controller_view_node = next(node for node in viewspec.nodes if node.id == "ctrl_1")
        assert controller_view_node.parent_id is None

    def test_ui_classes_from_status(self) -> None:
        """Test that UI classes are built from node status."""
        nodes = [
            {"node_id": "succeeded_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
            {"node_id": "failed_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.FAILED},
            {"node_id": "running_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.RUNNING},
        ]
        graph = self._make_graph(nodes=nodes)
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        succeeded_node = next(node for node in viewspec.nodes if node.id == "succeeded_1")
        assert "ok" in succeeded_node.ui["classes"]
        assert "succeeded" in succeeded_node.ui["classes"]

        failed_node = next(node for node in viewspec.nodes if node.id == "failed_1")
        assert "failed" in failed_node.ui["classes"]
        assert "error" in failed_node.ui["classes"]

        running_node = next(node for node in viewspec.nodes if node.id == "running_1")
        assert "running" in running_node.ui["classes"]

    def test_ui_badges_from_timing_and_metrics(self) -> None:
        """Test that UI badges are built from timing and metrics."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "test_pipe",
            "status": NodeStatus.SUCCEEDED,
            "timing": TimingSpec(
                started_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                ended_at=datetime(2024, 1, 15, 10, 30, 0, 132000, tzinfo=timezone.utc),
            ),
            "metrics": {"llm_tokens": 150.0, "cost_usd": 0.0015},
        }
        graph = self._make_graph(nodes=[node])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        view_node = viewspec.nodes[0]
        assert "badges" in view_node.ui
        badges = view_node.ui["badges"]
        assert "0.13s" in badges
        assert "150 tokens" in badges
        assert "$0.0015" in badges

    def test_inspector_data_populated(self) -> None:
        """Test that inspector data is populated correctly."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "extract_text",
            "pipe_type": "PipeLLM",
            "status": NodeStatus.SUCCEEDED,
            "timing": TimingSpec(
                started_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                ended_at=datetime(2024, 1, 15, 10, 30, 5, tzinfo=timezone.utc),
            ),
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input", concept="Text", preview="Hello", digest="digest_001")],
                outputs=[IOSpec(name="output", concept="Text", preview="World", digest="digest_002")],
            ),
            "tags": {"layer": "root"},
            "metrics": {"llm_tokens": 150.0},
        }
        graph = self._make_graph(nodes=[node])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        view_node = viewspec.nodes[0]
        assert view_node.inspector["pipe_code"] == "extract_text"
        assert view_node.inspector["pipe_type"] == "PipeLLM"
        assert "timing" in view_node.inspector
        assert "started_at" in view_node.inspector["timing"]
        assert "ended_at" in view_node.inspector["timing"]
        assert "io_preview" in view_node.inspector
        assert len(view_node.inspector["io_preview"]["inputs"]) == 1
        assert len(view_node.inspector["io_preview"]["outputs"]) == 1
        assert view_node.inspector["tags"] == {"layer": "root"}
        assert view_node.inspector["metrics"] == {"llm_tokens": 150.0}

    def test_view_index_built(self) -> None:
        """Test that ViewIndex is built correctly."""
        nodes = [
            {"node_id": "node_1", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_a", "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_2", "kind": NodeKind.OPERATOR, "pipe_code": "pipe_b", "status": NodeStatus.FAILED},
        ]
        edges = [
            {"edge_id": "edge_1", "source": "node_1", "target": "node_2", "kind": EdgeKind.CONTROL},
        ]
        graph = self._make_graph(nodes=nodes, edges=edges)
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        assert viewspec.index is not None
        assert "node_1" in viewspec.index.edges_by_node
        assert "edge_1" in viewspec.index.edges_by_node["node_1"]
        assert "pipe_code:pipe_a" in viewspec.index.search
        assert "node_1" in viewspec.index.search["pipe_code:pipe_a"]
        assert "status:failed" in viewspec.index.search
        assert "node_2" in viewspec.index.search["status:failed"]

    def test_contains_edges_skipped(self) -> None:
        """Test that CONTAINS edges are skipped (handled via parent_id)."""
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
            "edge_id": "edge_contains",
            "source": "ctrl_1",
            "target": "child_1",
            "kind": EdgeKind.CONTAINS,
        }
        control_edge = {
            "edge_id": "edge_control",
            "source": "child_1",
            "target": "node_2",
            "kind": EdgeKind.CONTROL,
        }
        other_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "step_b",
            "status": NodeStatus.SUCCEEDED,
        }
        graph = self._make_graph(nodes=[controller_node, child_node, other_node], edges=[contains_edge, control_edge])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        # CONTAINS edge should not be in ViewEdges
        contains_edge_ids = [edge.id for edge in viewspec.edges if edge.kind == EdgeKind.CONTAINS]
        assert len(contains_edge_ids) == 0

        # CONTROL edge should be present
        control_edge_ids = [edge.id for edge in viewspec.edges if edge.kind == EdgeKind.CONTROL]
        assert "edge_control" in control_edge_ids

    def test_show_data_edges_option(self) -> None:
        """Test that show_data_edges option filters DATA edges."""
        nodes = [
            {"node_id": "node_1", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
            {"node_id": "node_2", "kind": NodeKind.OPERATOR, "status": NodeStatus.SUCCEEDED},
        ]
        edges = [
            {"edge_id": "edge_data", "source": "node_1", "target": "node_2", "kind": EdgeKind.DATA},
            {"edge_id": "edge_control", "source": "node_1", "target": "node_2", "kind": EdgeKind.CONTROL},
        ]
        graph = self._make_graph(nodes=nodes, edges=edges)
        analysis = GraphAnalysis.from_graphspec(graph)

        # With show_data_edges=True (default)
        viewspec_with_data = graphspec_to_viewspec(graph, analysis, options={"show_data_edges": True})
        assert len(viewspec_with_data.edges) == 2

        # With show_data_edges=False
        viewspec_without_data = graphspec_to_viewspec(graph, analysis, options={"show_data_edges": False})
        assert len(viewspec_without_data.edges) == 1
        assert viewspec_without_data.edges[0].kind == EdgeKind.CONTROL

    def test_custom_layout_spec(self) -> None:
        """Test that custom LayoutSpec is used."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "status": NodeStatus.SUCCEEDED,
        }
        graph = self._make_graph(nodes=[node])
        analysis = GraphAnalysis.from_graphspec(graph)

        custom_layout = LayoutSpec(direction=FlowchartDirection.LEFT_TO_RIGHT, nodesep=100, ranksep=150)
        viewspec = graphspec_to_viewspec(graph, analysis, layout=custom_layout)

        assert viewspec.layout.direction == FlowchartDirection.LEFT_TO_RIGHT
        assert viewspec.layout.nodesep == 100
        assert viewspec.layout.ranksep == 150

    def test_source_metadata_populated(self) -> None:
        """Test that source metadata is populated from GraphSpec."""
        graph = GraphSpec(
            graph_id=self.GRAPH_ID,
            created_at=self.CREATED_AT,
            pipeline_ref=PipelineRef(domain="test_domain", main_pipe="test_main_pipe"),
            nodes=[],
            edges=[],
        )
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        assert viewspec.source["producer"] == f"pipelex {get_package_version()}"
        assert viewspec.source["domain"] == "test_domain"
        assert viewspec.source["main_pipe"] == "test_main_pipe"

    def test_node_label_from_pipe_code(self) -> None:
        """Test that node label uses pipe_code when available."""
        node_with_code = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "extract_text",
            "status": NodeStatus.SUCCEEDED,
        }
        node_without_code = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_type": "PipeLLM",
            "status": NodeStatus.SUCCEEDED,
        }
        node_with_nothing = {
            "node_id": "node_3",
            "kind": NodeKind.OPERATOR,
            "status": NodeStatus.SUCCEEDED,
        }
        graph = self._make_graph(nodes=[node_with_code, node_without_code, node_with_nothing])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        node1 = next(node for node in viewspec.nodes if node.id == "node_1")
        assert node1.label == "extract_text"

        node2 = next(node for node in viewspec.nodes if node.id == "node_2")
        assert node2.label == "PipeLLM"

        node3 = next(node for node in viewspec.nodes if node.id == "node_3")
        assert node3.label == "node_3"

    def test_error_in_inspector(self) -> None:
        """Test that error information is included in inspector."""
        node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "failed_pipe",
            "status": NodeStatus.FAILED,
            "error": ErrorSpec(error_type="PipeRunError", message="LLM generation failed", stack="Traceback..."),
        }
        graph = self._make_graph(nodes=[node])
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        view_node = viewspec.nodes[0]
        assert "error" in view_node.inspector
        assert view_node.inspector["error"]["error_type"] == "PipeRunError"
        assert view_node.inspector["error"]["message"] == "LLM generation failed"
        assert view_node.inspector["error"]["stack"] == "Traceback..."
