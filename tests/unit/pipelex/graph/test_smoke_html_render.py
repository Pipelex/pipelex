"""Bounded-size smoke check: catches a regression where assets get re-inlined."""

from datetime import datetime, timezone

from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec, NodeStatus, PipelineRef
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html


class TestSmokeHtmlRender:
    def test_rendered_html_stays_small_when_assets_externalized(self) -> None:
        node = NodeSpec(node_id="n1", kind=NodeKind.OPERATOR, pipe_code="hello", status=NodeStatus.SUCCEEDED)
        graph = GraphSpec(
            graph_id="smoke",
            created_at=datetime.now(timezone.utc),
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )
        config = get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config

        html = generate_reactflow_html(graph, config)

        assert "cdn.jsdelivr.net/npm/@pipelex/mthds-ui" in html
        assert "cdn.jsdelivr.net/npm/elkjs" in html
        assert "sha384-" in html
        # The full IIFE bundle is ~466 kB; if a future change accidentally inlines it,
        # this generous ceiling will catch the regression.
        assert len(html) < 50_000, f"HTML unexpectedly large ({len(html)} bytes) — assets may have been re-inlined"
