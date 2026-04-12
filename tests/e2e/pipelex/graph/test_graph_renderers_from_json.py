"""E2E test for generating all graph renderings from JSON input.

This test loads a GraphSpec from JSON and generates both Mermaid and ReactFlow
outputs in the same folder for easy comparison.
"""

from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.mermaidflow.mermaid_html import (
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.file_utils import get_incremental_directory_path, load_text_from_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.graph.test_data import GraphTestData


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder in TEST_OUTPUTS_DIR.

    Creates folders like: temp/test_outputs/graph_renderers/run_01, run_02, etc.
    """
    base_dir = str(Path(TEST_OUTPUTS_DIR) / "graph_renderers")
    return Path(get_incremental_directory_path(base_dir, "run"))


@pytest.mark.asyncio(loop_scope="class")
class TestGraphRenderersFromJson:
    """E2E tests for generating all graph renderings from JSON for comparison."""

    def _get_graph_config_with_data(self):
        """Get a graph config with all stuff data inclusion flags enabled."""
        base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
        new_data_inclusion = base_graph_config.data_inclusion.model_copy(
            update={
                "stuff_json_content": True,
                "stuff_text_content": True,
                "stuff_html_content": True,
            }
        )
        return base_graph_config.model_copy(update={"data_inclusion": new_data_inclusion})

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_all_renderers_from_json(self, topic: str, graph_json_path: str) -> None:
        """Generate all graph renderings (Mermaid + ReactFlow) in one folder.

        This test generates:

        - mermaidflow.mmd + mermaidflow.html (Mermaid mermaidflow view)
        - reactflow.html (ReactFlow interactive view)

        All outputs are saved in the same folder for easy comparison.
        """
        # Load graph from JSON
        json_path = Path(graph_json_path)
        assert json_path.exists(), f"Graph JSON file not found: {json_path}"

        json_str = load_text_from_path(str(json_path))
        graph_spec = GraphSpec.model_validate_json(json_str)
        assert graph_spec is not None
        assert len(graph_spec.nodes) > 0

        log.info(f"Loaded graph '{topic}' with {len(graph_spec.nodes)} nodes and {len(graph_spec.edges)} edges")

        # Create output directory
        output_dir = _get_next_output_folder()
        log.info(f"Saving all graph renderings to: {output_dir}")

        graph_config = self._get_graph_config_with_data()
        pretty_print(graph_config, title="Graph config")

        # ==================== MERMAID OUTPUTS ====================

        # Mermaidflow with data
        mermaidflow = MermaidflowFactory.make_from_graphspec(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "mermaidflow.mmd").write_text(mermaidflow.mermaid_code, encoding="utf-8")
        has_mermaidflow_data = mermaidflow.stuff_data or mermaidflow.stuff_data_text or mermaidflow.stuff_data_html
        if has_mermaidflow_data:
            mermaidflow_html = await render_mermaid_html_with_data_async(
                mermaidflow.mermaid_code,
                stuff_data=mermaidflow.stuff_data,
                stuff_data_text=mermaidflow.stuff_data_text,
                stuff_data_html=mermaidflow.stuff_data_html,
                stuff_metadata=mermaidflow.stuff_metadata,
                title=f"Mermaidflow (Interactive): {topic}",
            )
        else:
            mermaidflow_html = await render_mermaid_html_async(mermaidflow.mermaid_code, title=f"Mermaidflow: {topic}")
        (output_dir / "mermaidflow.html").write_text(mermaidflow_html, encoding="utf-8")

        # ==================== REACTFLOW OUTPUTS ====================

        # Generate ReactFlow HTML directly from GraphSpec
        reactflow_html = await generate_reactflow_html_async(
            graph_spec,
            graph_config.reactflow_config,
            title=f"ReactFlow: {topic}",
        )
        reactflow_path = output_dir / "reactflow.html"
        reactflow_path.write_text(reactflow_html, encoding="utf-8")

        # ==================== VERIFICATION ====================

        # Verify all files were created
        expected_files = [
            "mermaidflow.mmd",
            "mermaidflow.html",
            "reactflow.html",
        ]
        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Expected file not created: {file_path}"
            assert file_path.stat().st_size > 0, f"File is empty: {file_path}"

        # Verify stuff data collection was attempted when loading from JSON
        # Note: Results may be empty if the test data doesn't have data/data_text/data_html fields populated
        if graph_config.data_inclusion.stuff_json_content:
            assert mermaidflow.stuff_data is not None, "stuff_data should be collected when stuff_json_content=True"

        if graph_config.data_inclusion.stuff_text_content:
            assert mermaidflow.stuff_data_text is not None, "stuff_data_text should be collected when stuff_text_content=True"

        if graph_config.data_inclusion.stuff_html_content:
            assert mermaidflow.stuff_data_html is not None, "stuff_data_html should be collected when stuff_html_content=True"

        # Summary
        log.info(
            f"All renderings generated for '{topic}':\n"
            f"  Output: {output_dir}\n"
            f"  Mermaid:\n"
            f"     - mermaidflow.html\n"
            f"  ReactFlow:\n"
            f"     - reactflow.html"
        )
