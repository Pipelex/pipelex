"""E2E test for Mermaid diagram generation from JSON graph input.

This test loads a GraphSpec from JSON and verifies that Mermaid diagrams
and HTML can be generated correctly without requiring inference.
"""

from pathlib import Path

import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.mermaidflow.mermaid_html import (
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.file_utils import get_incremental_directory_path, load_text_from_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.graph.test_data import GraphTestData


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder in TEST_OUTPUTS_DIR.

    Creates folders like: temp/test_outputs/mermaid_from_json/run_01, run_02, etc.
    """
    base_dir = str(Path(TEST_OUTPUTS_DIR) / "mermaid_from_json")
    return Path(get_incremental_directory_path(base_dir, "run"))


@pytest.mark.asyncio(loop_scope="class")
class TestMermaidFromJson:
    """E2E tests for Mermaid diagram generation from JSON graph files."""

    def _get_graph_config_with_data(self):
        """Get a graph config with stuff data inclusion enabled."""
        base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
        new_data_inclusion = base_graph_config.data_inclusion.model_copy(update={"stuff_json_content": True})
        return base_graph_config.model_copy(update={"data_inclusion": new_data_inclusion})

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_mermaid_diagrams_from_json_graph(self, topic: str, graph_json_path: str) -> None:
        """Test generating Mermaid diagrams from a JSON graph file.

        This test:

        1. Loads a GraphSpec from JSON
        2. Generates mermaidflow Mermaid diagram
        3. Renders to HTML (with interactive data where applicable)
        4. Saves outputs to TEST_OUTPUTS_DIR
        5. Verifies the structure of generated diagrams and HTML
        """
        # Load graph from JSON
        json_path = Path(graph_json_path)
        assert json_path.exists(), f"Graph JSON file not found: {json_path}"

        json_str = load_text_from_path(str(json_path))
        graph_spec = GraphSpec.model_validate_json(json_str)

        # Verify graph loaded correctly
        assert graph_spec is not None
        assert len(graph_spec.nodes) > 0
        assert len(graph_spec.edges) > 0

        log.info(f"Loaded graph '{topic}' with {len(graph_spec.nodes)} nodes and {len(graph_spec.edges)} edges")

        # Save outputs to TEST_OUTPUTS_DIR
        output_dir = _get_next_output_folder()
        log.info(f"Saving Mermaid outputs to: {output_dir}")

        graph_config = self._get_graph_config_with_data()

        # Generate mermaidflow Mermaid with data
        mermaidflow = MermaidflowFactory.make_from_graphspec(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        assert mermaidflow.mermaid_code.startswith("flowchart TD")

        mermaidflow_mmd_path = output_dir / "mermaidflow.mmd"
        mermaidflow_mmd_path.write_text(mermaidflow.mermaid_code, encoding="utf-8")
        log.info(f"Saved mermaidflow.mmd: {mermaidflow_mmd_path}")
        log.info(f"Mermaidflow stuff_data count: {len(mermaidflow.stuff_data) if mermaidflow.stuff_data else 0}")

        if mermaidflow.stuff_data:
            mermaidflow_html = await render_mermaid_html_with_data_async(
                mermaidflow.mermaid_code,
                stuff_data=mermaidflow.stuff_data,
                stuff_metadata=mermaidflow.stuff_metadata,
                title=f"Mermaidflow (Interactive): {topic}",
            )
        else:
            mermaidflow_html = await render_mermaid_html_async(mermaidflow.mermaid_code, title=f"Mermaidflow: {topic}")

        mermaidflow_html_path = output_dir / "mermaidflow.html"
        mermaidflow_html_path.write_text(mermaidflow_html, encoding="utf-8")
        log.info(f"Saved mermaidflow.html: {mermaidflow_html_path}")

        # Verify all files were saved
        assert mermaidflow_mmd_path.exists()
        assert mermaidflow_html_path.exists()

        # Verify HTML structure
        html_content = mermaidflow_html_path.read_text(encoding="utf-8")
        assert html_content.startswith("<!DOCTYPE html>")
        assert "mermaid" in html_content
        assert 'class="mermaid"' in html_content

        log.info(f"✅ Mermaid generation complete for '{topic}':\n  - Mermaidflow: {mermaidflow_mmd_path.stat().st_size} bytes")

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_mermaidflow_structure(self, topic: str, graph_json_path: str) -> None:
        """Test that mermaidflow Mermaid combines orchestration and dataflow elements."""
        _ = topic  # Used for test identification

        json_str = load_text_from_path(graph_json_path)
        graph_spec = GraphSpec.model_validate_json(json_str)
        graph_config = self._get_graph_config_with_data()
        mermaidflow = MermaidflowFactory.make_from_graphspec(graph_spec, graph_config)

        mermaid_code = mermaidflow.mermaid_code

        # Verify mermaidflow has both orchestration elements (subgraphs) and dataflow elements (stuff)
        assert "flowchart" in mermaid_code
        assert "classDef stuff" in mermaid_code

        # Mermaidflow should have subgraphs for controllers
        assert "subgraph" in mermaid_code
