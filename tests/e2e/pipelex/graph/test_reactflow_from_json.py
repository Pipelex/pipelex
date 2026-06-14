"""E2E test for ReactFlow HTML generation from JSON graph input.

This test loads a GraphSpec from JSON and verifies that ReactFlow HTML
can be generated correctly without requiring inference.
"""

from pathlib import Path

import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.tools.misc.file_utils import get_incremental_directory_path, load_text_from_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.graph.test_data import GraphTestData


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder in TEST_OUTPUTS_DIR.

    Creates folders like: temp/test_outputs/reactflow_from_json/run_01, run_02, etc.
    """
    base_dir = Path(TEST_OUTPUTS_DIR) / "reactflow_from_json"
    return get_incremental_directory_path(base_dir, base_name="run")


class TestReactFlowFromJson:
    """E2E tests for ReactFlow HTML generation from JSON graph files."""

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_reactflow_html_from_json_graph(self, topic: str, graph_json_path: str) -> None:
        """Test generating ReactFlow HTML from a JSON graph file.

        This test:
        1. Loads a GraphSpec from JSON
        2. Generates ReactFlow HTML directly from GraphSpec
        3. Saves outputs to TEST_OUTPUTS_DIR
        4. Verifies the HTML structure and embedded data
        """
        # Load graph from JSON
        json_path = Path(graph_json_path)
        assert json_path.exists(), f"Graph JSON file not found: {json_path}"

        json_str = load_text_from_path(json_path)
        graph_spec = GraphSpec.model_validate_json(json_str)

        # Verify graph loaded correctly
        assert graph_spec is not None
        assert len(graph_spec.nodes) > 0
        assert len(graph_spec.edges) > 0

        # Generate ReactFlow HTML directly from GraphSpec
        rf_config = get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config
        reactflow_html = await generate_reactflow_html_async(graph_spec, rf_config, title=f"Graph: {topic}")

        # Save outputs to TEST_OUTPUTS_DIR
        output_dir = _get_next_output_folder()
        log.info(f"Saving ReactFlow outputs to: {output_dir}")

        # Save ReactFlow HTML
        reactflow_path = output_dir / "reactflow.html"
        reactflow_path.write_text(reactflow_html)
        log.info(f"Saved reactflow.html: {reactflow_path}")

        # Verify files were saved
        assert reactflow_path.exists()
        assert reactflow_path.stat().st_size > 1000

        # Verify HTML structure
        assert reactflow_html.startswith("<!DOCTYPE html>")
        assert '<script type="application/json" id="pipelex-graphspec">' in reactflow_html
        assert '<div id="root">' in reactflow_html
        assert f'"{graph_spec.graph_id}"' in reactflow_html

        # Verify GraphSpec JSON is embedded
        first_pipe_code = graph_spec.nodes[0].pipe_code
        if first_pipe_code is not None:
            assert first_pipe_code in reactflow_html

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_reactflow_html_graphspec_structure(self, topic: str, graph_json_path: str) -> None:
        """Test that GraphSpec is correctly embedded in HTML."""
        _ = topic  # Used for test identification

        # Load graph from JSON
        json_str = load_text_from_path(Path(graph_json_path))
        graph_spec = GraphSpec.model_validate_json(json_str)

        # Generate ReactFlow HTML
        rf_config = get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config
        reactflow_html = await generate_reactflow_html_async(graph_spec, rf_config, title="Test Graph")

        # Verify GraphSpec is embedded
        assert '<script type="application/json" id="pipelex-graphspec">' in reactflow_html

        # ViewSpec should NOT be present
        assert 'id="pipelex-viewspec"' not in reactflow_html
