"""Unit tests for the ViewSpec models."""

from datetime import datetime, timezone

from pipelex.graph.reactflow.viewspec import (
    CURRENT_VIEWSPEC_VERSION,
    LayoutSpec,
    PayloadSpec,
    ViewEdge,
    ViewIndex,
    ViewNode,
    ViewSpec,
)
from pipelex.tools.misc.chart_utils import FlowchartDirection


class TestViewNode:
    """Tests for the ViewNode model."""

    def test_minimal_view_node(self) -> None:
        """Test creating a minimal ViewNode with required fields."""
        node = ViewNode(id="node_1", label="Test Node", kind="operator")
        assert node.id == "node_1"
        assert node.label == "Test Node"
        assert node.kind == "operator"
        assert node.status is None
        assert node.type == "default"
        assert node.parent_id is None
        assert node.position is None
        assert node.size is None
        assert node.ui == {}
        assert node.inspector == {}
        assert node.handles is None

    def test_view_node_with_all_fields(self) -> None:
        """Test creating a ViewNode with all optional fields."""
        node = ViewNode(
            id="node_1",
            label="Test Node",
            kind="operator",
            status="succeeded",
            type="operator",
            parent_id="ctrl_1",
            extent="parent",
            position={"x": 100.0, "y": 200.0},
            size={"width": 150.0, "height": 50.0},
            ui={"badges": ["132ms"], "classes": ["ok"], "icon": "llm"},
            inspector={
                "pipe_code": "extract_text",
                "pipe_type": "PipeLLM",
                "timing": {"started_at": "2024-01-15T10:30:00+00:00", "ended_at": "2024-01-15T10:30:00.132000+00:00"},
            },
            handles=[{"id": "out.text", "type": "source", "position": "Right"}],
        )
        assert node.id == "node_1"
        assert node.status == "succeeded"
        assert node.type == "operator"
        assert node.parent_id == "ctrl_1"
        assert node.extent == "parent"
        assert node.position == {"x": 100.0, "y": 200.0}
        assert node.size == {"width": 150.0, "height": 50.0}
        assert node.ui["badges"] == ["132ms"]
        assert node.inspector["pipe_code"] == "extract_text"
        assert node.handles is not None
        assert len(node.handles) == 1

    def test_view_node_defaults(self) -> None:
        """Test that ViewNode has correct defaults."""
        node = ViewNode(id="node_1", label="Test", kind="operator")
        assert node.type == "default"
        assert node.ui == {}
        assert node.inspector == {}


class TestViewEdge:
    """Tests for the ViewEdge model."""

    def test_minimal_view_edge(self) -> None:
        """Test creating a minimal ViewEdge with required fields."""
        edge = ViewEdge(id="edge_1", source="node_1", target="node_2", kind="control")
        assert edge.id == "edge_1"
        assert edge.source == "node_1"
        assert edge.target == "node_2"
        assert edge.kind == "control"
        assert edge.label is None
        assert edge.type == "default"
        assert edge.animated is None
        assert edge.hidden is False
        assert edge.source_handle is None
        assert edge.target_handle is None
        assert edge.ui == {}

    def test_view_edge_with_all_fields(self) -> None:
        """Test creating a ViewEdge with all optional fields."""
        edge = ViewEdge(
            id="edge_1",
            source="node_1",
            target="node_2",
            kind="data",
            label="output_data",
            type="data",
            animated=True,
            hidden=False,
            source_handle="out.data",
            target_handle="in.data",
            ui={"classes": ["dashed"], "markerEnd": "arrow"},
        )
        assert edge.label == "output_data"
        assert edge.type == "data"
        assert edge.animated is True
        assert edge.source_handle == "out.data"
        assert edge.target_handle == "in.data"
        assert edge.ui["classes"] == ["dashed"]


class TestLayoutSpec:
    """Tests for the LayoutSpec model."""

    def test_default_layout_spec(self) -> None:
        """Test that LayoutSpec has correct defaults."""
        layout = LayoutSpec()
        assert layout.engine == "dagre"
        assert layout.direction == FlowchartDirection.TOP_DOWN
        assert layout.nodesep == 50
        assert layout.ranksep == 80
        assert layout.align is None
        assert layout.allow_manual_positions is True

    def test_custom_layout_spec(self) -> None:
        """Test creating a LayoutSpec with custom values."""
        layout = LayoutSpec(
            engine="dagre",
            direction=FlowchartDirection.LEFT_TO_RIGHT,
            nodesep=100,
            ranksep=150,
            align="UL",
            allow_manual_positions=False,
        )
        assert layout.direction == FlowchartDirection.LEFT_TO_RIGHT
        assert layout.nodesep == 100
        assert layout.ranksep == 150
        assert layout.align == "UL"
        assert layout.allow_manual_positions is False


class TestViewIndex:
    """Tests for the ViewIndex model."""

    def test_empty_view_index(self) -> None:
        """Test creating an empty ViewIndex."""
        index = ViewIndex()
        assert index.edges_by_node == {}
        assert index.children_by_parent == {}
        assert index.search == {}

    def test_view_index_with_data(self) -> None:
        """Test creating a ViewIndex with data."""
        index = ViewIndex(
            edges_by_node={"node_1": ["edge_1", "edge_2"]},
            children_by_parent={"ctrl_1": ["node_1", "node_2"]},
            search={"pipe_code:extract_text": ["node_1"], "status:failed": ["node_2"]},
        )
        assert index.edges_by_node["node_1"] == ["edge_1", "edge_2"]
        assert index.children_by_parent["ctrl_1"] == ["node_1", "node_2"]
        assert index.search["pipe_code:extract_text"] == ["node_1"]


class TestPayloadSpec:
    """Tests for the PayloadSpec model."""

    def test_default_payload_spec(self) -> None:
        """Test that PayloadSpec has correct defaults."""
        payload = PayloadSpec()
        assert payload.mode == "inline"
        assert payload.base_path is None
        assert payload.by_digest == {}

    def test_external_payload_spec(self) -> None:
        """Test creating an external PayloadSpec."""
        payload = PayloadSpec(
            mode="external",
            base_path="/data/payloads",
            by_digest={"digest_001": "payload_001.json", "digest_002": "payload_002.json"},
        )
        assert payload.mode == "external"
        assert payload.base_path == "/data/payloads"
        assert payload.by_digest["digest_001"] == "payload_001.json"


class TestViewSpec:
    """Tests for the ViewSpec model."""

    def test_minimal_view_spec(self) -> None:
        """Test creating a minimal ViewSpec with required fields."""
        viewspec = ViewSpec(
            created_at=datetime.now(timezone.utc),
            graph_id="graph_001",
        )
        assert viewspec.schema_version == CURRENT_VIEWSPEC_VERSION
        assert viewspec.graph_id == "graph_001"
        assert viewspec.engine == "reactflow"
        assert viewspec.source == {}
        assert viewspec.options == {}
        assert isinstance(viewspec.layout, LayoutSpec)
        assert viewspec.nodes == []
        assert viewspec.edges == []
        assert viewspec.index is None
        assert viewspec.payloads is None

    def test_view_spec_with_all_fields(self) -> None:
        """Test creating a ViewSpec with all fields."""
        node = ViewNode(id="node_1", label="Test Node", kind="operator")
        edge = ViewEdge(id="edge_1", source="node_1", target="node_2", kind="control")
        index = ViewIndex(edges_by_node={"node_1": ["edge_1"]})
        payload = PayloadSpec(mode="inline")
        layout = LayoutSpec(direction=FlowchartDirection.LEFT_TO_RIGHT)

        viewspec = ViewSpec(
            created_at=datetime.now(timezone.utc),
            graph_id="graph_001",
            source={"graph_schema_version": "1.0", "producer": "pipelex 0.9.3"},
            options={"show_data_edges": True, "collapse_controllers": False},
            layout=layout,
            nodes=[node],
            edges=[edge],
            index=index,
            payloads=payload,
        )

        assert viewspec.graph_id == "graph_001"
        assert viewspec.source["producer"] == "pipelex 0.9.3"
        assert viewspec.options["show_data_edges"] is True
        assert viewspec.layout.direction == FlowchartDirection.LEFT_TO_RIGHT
        assert len(viewspec.nodes) == 1
        assert len(viewspec.edges) == 1
        assert viewspec.index is not None
        assert viewspec.index.edges_by_node["node_1"] == ["edge_1"]
        assert viewspec.payloads is not None

    def test_view_spec_serialization(self) -> None:
        """Test that ViewSpec can be serialized to JSON."""
        node = ViewNode(id="node_1", label="Test Node", kind="operator", position={"x": 100.0, "y": 200.0})
        viewspec = ViewSpec(
            created_at=datetime.now(timezone.utc),
            graph_id="graph_001",
            nodes=[node],
        )

        # Serialize to dict (Pydantic handles JSON serialization)
        data = viewspec.model_dump()
        assert data["graph_id"] == "graph_001"
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "node_1"
        assert data["nodes"][0]["position"] == {"x": 100.0, "y": 200.0}

    def test_view_spec_deserialization(self) -> None:
        """Test that ViewSpec can be deserialized from dict."""
        created_at = datetime.now(timezone.utc)
        data = {
            "schema_version": CURRENT_VIEWSPEC_VERSION,
            "created_at": created_at,
            "graph_id": "graph_001",
            "engine": "reactflow",
            "source": {},
            "options": {},
            "layout": {"engine": "dagre", "direction": "top_down"},
            "nodes": [{"id": "node_1", "label": "Test", "kind": "operator"}],
            "edges": [],
        }

        viewspec = ViewSpec.model_validate(data)
        assert viewspec.graph_id == "graph_001"
        assert len(viewspec.nodes) == 1
        assert viewspec.nodes[0].id == "node_1"

    def test_view_spec_default_layout(self) -> None:
        """Test that ViewSpec creates default LayoutSpec if not provided."""
        viewspec = ViewSpec(
            created_at=datetime.now(timezone.utc),
            graph_id="graph_001",
        )
        assert isinstance(viewspec.layout, LayoutSpec)
        assert viewspec.layout.engine == "dagre"
        assert viewspec.layout.direction == FlowchartDirection.TOP_DOWN
