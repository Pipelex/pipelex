"""Unit tests for the ReactFlow HTML generator (standalone mthds-ui bundle)."""

import re
from datetime import datetime, timezone

from pipelex.config import get_config
from pipelex.graph.csp import CSP_NONCE_SENTINEL
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html


class TestReactFlowHtml:
    """Tests for generate_reactflow_html function."""

    def _rf_config(self) -> ReactFlowRenderingConfig:
        """Get the default ReactFlow config for testing."""
        return get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config

    def _empty_graphspec(self) -> GraphSpec:
        """Create an empty GraphSpec for testing."""
        return GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(timezone.utc),
            pipeline_ref=PipelineRef(),
            nodes=[],
            edges=[],
        )

    def test_generates_html_with_embedded_graphspec(self) -> None:
        """Test that HTML contains embedded GraphSpec as JSON."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert "<!DOCTYPE html>" in html
        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert "test_graph" in html

    def test_embeds_config_json(self) -> None:
        """Test that viewer config is embedded as JSON."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert '<script type="application/json" id="pipelex-config">' in html

    def test_custom_title_in_html(self) -> None:
        """Test that custom title appears in HTML."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config(), title="My Custom Graph")

        assert "<title>My Custom Graph</title>" in html

    def test_full_graphspec_serialized_with_aliases(self) -> None:
        """Test that GraphSpec uses JSON aliases (id, not node_id)."""
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

        html = generate_reactflow_html(graph, self._rf_config())

        # Node should use alias "id" not Python field name "node_id"
        assert '"id": "node_1"' in html
        assert '"node_id"' not in html
        assert "test_pipe" in html

    def test_html_is_valid_structure(self) -> None:
        """Test that generated HTML has valid structure."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "</html>" in html
        assert '<div id="root">' in html

    def test_html_contains_bundled_js(self) -> None:
        """Test that HTML includes the mthds-ui GraphViewer bundle."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        # The bundled IIFE should be present (minified React + ReactFlow + mthds-ui)
        assert '"use strict"' in html
        # Should NOT contain old Jinja2/dagre references
        assert "getLayoutedElements" not in html or "elkjs" in html  # ELK, not dagre

    def test_html_contains_csp_nonce_on_inline_script(self) -> None:
        """Verify the inline script tag has the CSP nonce sentinel."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        pattern = rf'<script nonce="{re.escape(CSP_NONCE_SENTINEL)}">'
        assert re.search(pattern, html), "Inline <script> should have the CSP nonce sentinel"

    def test_html_contains_csp_nonce_on_inline_style(self) -> None:
        """Verify the inline style tag has the CSP nonce sentinel."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert f'<style nonce="{CSP_NONCE_SENTINEL}">' in html

    def test_json_data_scripts_have_no_nonce(self) -> None:
        """Verify application/json script tags do NOT have a nonce attribute."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        json_scripts = re.findall(r'<script type="application/json"[^>]*>', html)
        assert len(json_scripts) >= 2, "Expected at least 2 JSON data script tags (graphspec + config)"
        for tag in json_scripts:
            assert "nonce" not in tag, f"JSON data script should not have nonce: {tag}"

    def test_no_csp_meta_tag(self) -> None:
        """Verify no CSP meta tag is present (standalone HTML should be CSP-free)."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert "Content-Security-Policy" not in html

    def test_script_tag_count(self) -> None:
        """Verify exactly 3 closing script tags (graphspec, config, IIFE)."""
        html = generate_reactflow_html(self._empty_graphspec(), self._rf_config())

        assert html.count("</script>") == 3
