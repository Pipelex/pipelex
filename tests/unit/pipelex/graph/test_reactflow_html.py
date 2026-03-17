"""Unit tests for the ReactFlow HTML generator."""

import re
from datetime import datetime, timezone

import pytest

from pipelex.config import get_config
from pipelex.core.stuffs.stuff_template_set import STUFF_TEMPLATE_SET
from pipelex.graph.csp import CSP_NONCE_SENTINEL
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html
from pipelex.graph.reactflow.template_set import REACTFLOW_TEMPLATE_SET
from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


class TestReactFlowHtml:
    """Tests for generate_reactflow_html function."""

    @pytest.fixture(autouse=True)
    def setup_templates(self) -> None:
        """Ensure ReactFlow and shared templates are loaded before tests."""
        TemplateRegistry.clear()
        TemplateLoader.reset()
        # Load stuff templates first (used by ReactFlow templates)
        stuff_name, stuff_package, stuff_templates = STUFF_TEMPLATE_SET
        TemplateLoader.register_set(
            name=stuff_name,
            package=stuff_package,
            templates=stuff_templates,
        )
        TemplateLoader.load("stuff")
        # Load ReactFlow templates
        reactflow_name, reactflow_package, reactflow_templates = REACTFLOW_TEMPLATE_SET
        TemplateLoader.register_set(
            name=reactflow_name,
            package=reactflow_package,
            templates=reactflow_templates,
        )
        TemplateLoader.load("reactflow")

    @pytest.fixture
    def rf_config(self) -> ReactFlowRenderingConfig:
        """Get the default ReactFlow config for testing."""
        return get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config

    @pytest.fixture
    def empty_graphspec(self) -> GraphSpec:
        """Create an empty GraphSpec for testing."""
        return GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(timezone.utc),
            pipeline_ref=PipelineRef(),
            nodes=[],
            edges=[],
        )

    def test_generates_html_with_embedded_graphspec(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that HTML contains embedded GraphSpec as JSON."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert "<!DOCTYPE html>" in html
        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert "test_graph" in html

    def test_embeds_graphspec_always(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that GraphSpec is always embedded."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert "test_graph" in html

    def test_no_viewspec_in_html(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that ViewSpec script tag is no longer present."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert 'id="pipelex-viewspec"' not in html

    def test_cdn_mode_includes_cdn_scripts(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that CDN mode includes CDN script tags."""
        cdn_config = rf_config.model_copy(update={"is_use_cdn": True})
        html = generate_reactflow_html(empty_graphspec, cdn_config)

        assert "unpkg.com/react@18" in html
        assert "unpkg.com/react-dom@18" in html
        assert "unpkg.com/reactflow@11" in html
        assert "unpkg.com/dagre@0.8.5" in html

    def test_custom_title_in_html(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that custom title appears in HTML."""
        html = generate_reactflow_html(empty_graphspec, rf_config, title="My Custom Graph")

        assert "<title>My Custom Graph</title>" in html

    def test_includes_reactflow_viewer_code(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that HTML includes ReactFlow viewer JavaScript."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert "ReactFlow" in html
        assert "getLayoutedElements" in html
        assert "onNodeClick" in html
        assert "inspector" in html

    def test_includes_inspector_panel(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that HTML includes inspector panel markup."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert 'id="inspector"' in html
        assert "inspector-panel" in html
        assert "closeInspector" in html

    def test_full_graphspec_serialized(self, rf_config: ReactFlowRenderingConfig) -> None:
        """Test that full GraphSpec with nodes is serialized."""
        node = NodeSpec(
            node_id="node_1",
            kind=NodeKind.OPERATOR,
            pipe_code="test_pipe",
            status=NodeStatus.SUCCEEDED,
        )
        graph = GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(timezone.utc),
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )

        html = generate_reactflow_html(graph, rf_config)

        # GraphSpec should be embedded with node data
        assert "node_1" in html
        assert "test_pipe" in html

    def test_html_is_valid_structure(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that generated HTML has valid structure."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        # Check for essential HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html
        assert '<div id="root">' in html

    def test_dagre_layout_included(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Test that Dagre layout function is included."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert "dagre" in html
        assert "getLayoutedElements" in html
        assert "rankdir" in html

    def test_html_contains_csp_nonce_on_inline_script(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Verify the inline script tag has the CSP nonce sentinel."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        # The main inline <script nonce="..."> (not type="application/json")
        pattern = rf'<script nonce="{re.escape(CSP_NONCE_SENTINEL)}">'
        assert re.search(pattern, html), "Inline <script> should have the CSP nonce sentinel"

    def test_html_contains_csp_nonce_on_inline_style(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Verify the inline style tag has the CSP nonce sentinel."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert f'<style nonce="{CSP_NONCE_SENTINEL}">' in html

    def test_html_contains_csp_nonce_on_cdn_scripts(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Verify CDN script tags have the CSP nonce sentinel."""
        cdn_config = rf_config.model_copy(update={"is_use_cdn": True})
        html = generate_reactflow_html(empty_graphspec, cdn_config)

        # All CDN <script src="..."> tags should have nonce
        cdn_scripts = re.findall(r'<script [^>]*src="https?://[^"]*"[^>]*>', html)
        assert len(cdn_scripts) >= 5, f"Expected at least 5 CDN script tags, found {len(cdn_scripts)}"
        for tag in cdn_scripts:
            assert f'nonce="{CSP_NONCE_SENTINEL}"' in tag, f"CDN script missing nonce: {tag}"

    def test_json_data_scripts_have_no_nonce(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Verify application/json script tags do NOT have a nonce attribute."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        json_scripts = re.findall(r'<script type="application/json"[^>]*>', html)
        assert len(json_scripts) >= 1, "Expected at least 1 JSON data script tag"
        for tag in json_scripts:
            assert "nonce" not in tag, f"JSON data script should not have nonce: {tag}"

    def test_html_has_no_csp_meta_tag(self, rf_config: ReactFlowRenderingConfig, empty_graphspec: GraphSpec) -> None:
        """Verify no CSP meta tag is present (standalone HTML should be CSP-free)."""
        html = generate_reactflow_html(empty_graphspec, rf_config)

        assert "Content-Security-Policy" not in html
