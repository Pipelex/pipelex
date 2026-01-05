"""Unit tests for the ReactFlow HTML generator."""

from datetime import UTC, datetime

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.reactflow_html import generate_reactflow_html
from pipelex.graph.viewspec import ViewSpec
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec


class TestReactFlowHtml:
    """Tests for generate_reactflow_html function."""

    def test_generates_html_with_embedded_viewspec(self) -> None:
        """Test that HTML contains embedded ViewSpec as JSON."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        assert "<!DOCTYPE html>" in html
        assert '<script type="application/json" id="pipelex-viewspec">' in html
        assert "test_graph" in html
        assert "const viewspec = JSON.parse" in html

    def test_embeds_graphspec_when_provided(self) -> None:
        """Test that GraphSpec is embedded when provided."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        graphspec = GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(UTC),
            pipeline_ref=PipelineRef(),
            nodes=[],
            edges=[],
        )
        html = generate_reactflow_html(viewspec, graphspec=graphspec)

        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert "test_graph" in html

    def test_does_not_embed_graphspec_when_not_provided(self) -> None:
        """Test that GraphSpec script tag is not present when not provided."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        # Should not have graphspec script tag
        assert '<script type="application/json" id="pipelex-graphspec">' not in html

    def test_cdn_mode_includes_cdn_scripts(self) -> None:
        """Test that CDN mode includes CDN script tags."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec, use_cdn=True)

        assert "unpkg.com/react@18" in html
        assert "unpkg.com/react-dom@18" in html
        assert "unpkg.com/@xyflow/react@11" in html
        assert "unpkg.com/dagre@0.8.5" in html

    def test_custom_title_in_html(self) -> None:
        """Test that custom title appears in HTML."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec, title="My Custom Graph")

        assert "<title>My Custom Graph</title>" in html

    def test_includes_reactflow_viewer_code(self) -> None:
        """Test that HTML includes ReactFlow viewer JavaScript."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        assert "ReactFlow" in html
        assert "getLayoutedElements" in html
        assert "onNodeClick" in html
        assert "inspector" in html

    def test_includes_inspector_panel(self) -> None:
        """Test that HTML includes inspector panel markup."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        assert 'id="inspector"' in html
        assert "inspector-panel" in html
        assert "closeInspector" in html

    def test_full_viewspec_serialized(self) -> None:
        """Test that full ViewSpec with nodes and edges is serialized."""
        # Create a simple graph and convert to ViewSpec
        node = NodeSpec(
            node_id="node_1",
            kind=NodeKind.OPERATOR,
            pipe_code="test_pipe",
            status=NodeStatus.SUCCEEDED,
        )
        graph = GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(UTC),
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )
        analysis = GraphAnalysis.from_graphspec(graph)
        viewspec = graphspec_to_viewspec(graph, analysis)

        html = generate_reactflow_html(viewspec)

        # ViewSpec should be embedded with node data
        assert "node_1" in html
        assert "test_pipe" in html

    def test_html_is_valid_structure(self) -> None:
        """Test that generated HTML has valid structure."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        # Check for essential HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html
        assert '<div id="root">' in html

    def test_dagre_layout_included(self) -> None:
        """Test that Dagre layout function is included."""
        viewspec = ViewSpec(
            created_at=datetime.now(UTC),
            graph_id="test_graph",
        )
        html = generate_reactflow_html(viewspec)

        assert "dagre" in html
        assert "getLayoutedElements" in html
        assert "rankdir" in html
