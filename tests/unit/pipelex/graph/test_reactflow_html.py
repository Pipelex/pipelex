"""Unit tests for the ReactFlow HTML generator (mthds-ui standalone bundle via Jinja2)."""

from datetime import UTC, datetime

from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html
from pipelex.graph.reactflow.standalone_assets import ELKJS, MTHDS_UI_CSS, MTHDS_UI_JS


class TestReactFlowHtml:
    """Tests for generate_reactflow_html function."""

    def _rf_config(self) -> ReactFlowRenderingConfig:
        return get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config

    def _empty_graphspec(self) -> GraphSpec:
        return GraphSpec(
            graph_id="test_graph",
            created_at=datetime.now(UTC),
            pipeline_ref=PipelineRef(),
            nodes=[],
            edges=[],
        )

    def test_generates_html_with_embedded_graphspec(self) -> None:
        """Test that HTML contains embedded GraphSpec as JSON."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert "<!DOCTYPE html>" in html
        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert "test_graph" in html

    def test_embeds_config_json(self) -> None:
        """Test that viewer config is embedded as JSON."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert '<script type="application/json" id="pipelex-config">' in html

    def test_custom_title_in_html(self) -> None:
        """Test that custom title appears in HTML."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config(), title="My Custom Graph")

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
            created_at=datetime.now(UTC),
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )

        html = generate_reactflow_html(graph, config=self._rf_config())

        assert '"id": "node_1"' in html
        assert '"node_id"' not in html
        assert "test_pipe" in html

    def test_html_is_valid_structure(self) -> None:
        """Test that generated HTML has valid structure."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html
        assert '<div id="root">' in html

    def test_html_loads_mthds_ui_js_from_cdn_with_sri(self) -> None:
        """The HTML must reference the pinned mthds-ui JS bundle on jsDelivr with SRI."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        expected = f'<script src="{MTHDS_UI_JS.url}" integrity="{MTHDS_UI_JS.integrity}" crossorigin="{MTHDS_UI_JS.crossorigin}"></script>'
        assert expected in html

    def test_html_loads_mthds_ui_css_from_cdn_with_sri(self) -> None:
        """The HTML must reference the pinned mthds-ui CSS on jsDelivr with SRI."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        expected = f'<link rel="stylesheet" href="{MTHDS_UI_CSS.url}" integrity="{MTHDS_UI_CSS.integrity}" crossorigin="{MTHDS_UI_CSS.crossorigin}">'
        assert expected in html

    def test_html_loads_elkjs_from_jsdelivr_with_sri(self) -> None:
        """Elkjs must come from jsDelivr (not unpkg) and carry an SRI hash."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        expected = f'<script src="{ELKJS.url}" integrity="{ELKJS.integrity}" crossorigin="{ELKJS.crossorigin}"></script>'
        assert expected in html
        assert "unpkg.com/elkjs" not in html

    def test_html_does_not_inline_bundle_contents(self) -> None:
        """Bundle bytes must not be inlined — externalized via <link>/<script src>."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        # Tokens that only exist inside the IIFE bundle / CSS bundle.
        assert '"use strict"' not in html
        assert ".react-flow" not in html
        assert "<style>" not in html

    def test_json_data_scripts_have_no_nonce(self) -> None:
        """Verify application/json script tags do NOT have a nonce attribute."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert '<script type="application/json" id="pipelex-graphspec">' in html
        assert '<script type="application/json" id="pipelex-config">' in html

    def test_no_csp_meta_tag(self) -> None:
        """Verify no CSP meta tag is present."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert "Content-Security-Policy" not in html

    def test_script_tag_count(self) -> None:
        """Verify exactly 4 closing script tags (graphspec, config, elkjs CDN, IIFE)."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert html.count("</script>") == 4

    def test_no_legacy_toolbar(self) -> None:
        """Verify the old hand-rendered toolbar is gone; mthds-ui v0.6+ owns chrome."""
        html = generate_reactflow_html(self._empty_graphspec(), config=self._rf_config())

        assert '<div class="toolbar">' not in html
        assert 'id="direction-toggle"' not in html
        assert 'id="controllers-toggle"' not in html
        assert 'id="zoom-in"' not in html
        assert 'id="zoom-out"' not in html
        assert 'id="zoom-fit"' not in html
        assert 'id="theme-toggle"' not in html
