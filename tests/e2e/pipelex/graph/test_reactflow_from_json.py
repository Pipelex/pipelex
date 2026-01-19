"""E2E test for ReactFlow HTML generation from JSON graph input.

This test loads a GraphSpec from JSON and verifies that ReactFlow HTML
can be generated correctly without requiring inference.
"""

from pathlib import Path

import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.graph.reactflow.viewspec_transformer import graphspec_to_viewspec
from pipelex.tools.misc.file_utils import get_incremental_directory_path, load_text_from_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.graph.test_data import GraphTestData


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder in TEST_OUTPUTS_DIR.

    Creates folders like: temp/test_outputs/reactflow_from_json/run_01, run_02, etc.
    """
    base_dir = str(Path(TEST_OUTPUTS_DIR) / "reactflow_from_json")
    return Path(get_incremental_directory_path(base_dir, "run"))


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
        2. Creates ViewSpec via transformer
        3. Generates ReactFlow HTML
        4. Saves outputs to TEST_OUTPUTS_DIR
        5. Verifies the HTML structure and embedded data
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

        # Create ViewSpec
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        # Verify ViewSpec structure
        assert viewspec.graph_id == graph_spec.graph_id
        assert len(viewspec.nodes) == len(graph_spec.nodes)
        assert viewspec.index is not None

        # Generate ReactFlow HTML
        rf_config = get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config
        reactflow_html = await generate_reactflow_html_async(viewspec, rf_config, graphspec=graph_spec, title=f"Graph: {topic}")

        # Save outputs to TEST_OUTPUTS_DIR
        output_dir = _get_next_output_folder()
        log.info(f"Saving ReactFlow outputs to: {output_dir}")

        # Save ViewSpec JSON
        viewspec_path = output_dir / "viewspec.json"
        viewspec_path.write_text(viewspec.model_dump_json(indent=2))
        log.info(f"Saved viewspec.json: {viewspec_path}")

        # Save ReactFlow HTML
        reactflow_path = output_dir / "reactflow.html"
        reactflow_path.write_text(reactflow_html)
        log.info(f"Saved reactflow.html: {reactflow_path}")

        # Verify files were saved
        assert viewspec_path.exists()
        assert reactflow_path.exists()
        assert reactflow_path.stat().st_size > 1000

        # Verify HTML structure
        assert reactflow_html.startswith("<!DOCTYPE html>")
        assert '<script type="application/json" id="pipelex-viewspec">' in reactflow_html
        assert '<script type="application/json" id="pipelex-graphspec">' in reactflow_html
        assert "ReactFlow" in reactflow_html
        assert "getLayoutedElements" in reactflow_html
        assert f'"{graph_spec.graph_id}"' in reactflow_html

        # Verify ViewSpec JSON is embedded
        assert viewspec.nodes[0].id in reactflow_html
        assert viewspec.nodes[0].label in reactflow_html

        # Verify GraphSpec JSON is embedded
        assert graph_spec.nodes[0].node_id in reactflow_html

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_reactflow_html_without_graphspec(self, topic: str, graph_json_path: str) -> None:
        """Test generating ReactFlow HTML without embedding GraphSpec."""
        _ = topic  # Used for test identification

        # Load graph from JSON
        json_str = load_text_from_path(graph_json_path)
        graph_spec = GraphSpec.model_validate_json(json_str)

        # Create ViewSpec
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        # Generate ReactFlow HTML without GraphSpec
        rf_config = get_config().pipelex.pipeline_execution_config.graph_config.reactflow_config
        reactflow_html = await generate_reactflow_html_async(viewspec, rf_config, graphspec=None, title="Test Graph")

        # Verify ViewSpec is embedded
        assert '<script type="application/json" id="pipelex-viewspec">' in reactflow_html

        # Verify GraphSpec is NOT embedded
        assert '<script type="application/json" id="pipelex-graphspec">' not in reactflow_html

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_reactflow_html_viewspec_structure(self, topic: str, graph_json_path: str) -> None:
        """Test that ViewSpec contains all expected data from the graph."""
        _ = topic  # Used for test identification

        # Load graph from JSON
        json_str = load_text_from_path(graph_json_path)
        graph_spec = GraphSpec.model_validate_json(json_str)

        # Create ViewSpec
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        # Verify node mapping
        assert len(viewspec.nodes) == len(graph_spec.nodes)
        for view_node in viewspec.nodes:
            # Find corresponding GraphSpec node
            graph_node = graph_spec.nodes[0]
            for node in graph_spec.nodes:
                if node.node_id == view_node.id:
                    graph_node = node
                    break

            # Verify basic mapping
            assert view_node.id == graph_node.node_id
            assert view_node.kind == graph_node.kind
            assert view_node.status == graph_node.status

            # Verify inspector data
            if graph_node.pipe_code:
                assert view_node.inspector["pipe_code"] == graph_node.pipe_code

        # Verify edge mapping (excluding CONTAINS edges)
        contains_edges = [edge for edge in graph_spec.edges if edge.kind.value == "contains"]
        expected_edge_count = len(graph_spec.edges) - len(contains_edges)
        assert len(viewspec.edges) == expected_edge_count

        # Verify index
        assert viewspec.index is not None
        assert len(viewspec.index.edges_by_node) > 0
        assert len(viewspec.index.children_by_parent) > 0
