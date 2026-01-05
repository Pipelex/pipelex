"""E2E test for generating all graph renderings from JSON input.

This test loads a GraphSpec from JSON and generates both Mermaid and ReactFlow
outputs in the same folder for easy comparison.
"""

from pathlib import Path

import pytest

from pipelex import log
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec_io import load_graphspec
from pipelex.graph.mermaid import (
    FlowchartDirection,
    graphspec_to_combo_mermaid_with_data,
    graphspec_to_dataflow_mermaid_with_data,
    graphspec_to_orchestration_mermaid,
)
from pipelex.graph.reactflow_html import generate_reactflow_html_async
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.mermaid_utils import (
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
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

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_all_renderers_from_json(self, topic: str, graph_json_path: str) -> None:
        """Generate all graph renderings (Mermaid + ReactFlow) in one folder.

        This test generates:

        - orchestration.mmd + orchestration.html (Mermaid orchestration view)
        - dataflow.mmd + dataflow.html (Mermaid dataflow view)
        - combo.mmd + combo.html (Mermaid combo view)
        - reactflow.html (ReactFlow interactive view)
        - viewspec.json (ViewSpec used by ReactFlow)

        All outputs are saved in the same folder for easy comparison.
        """
        # Load graph from JSON
        json_path = Path(graph_json_path)
        assert json_path.exists(), f"Graph JSON file not found: {json_path}"

        graph_spec = load_graphspec(json_path)
        assert graph_spec is not None
        assert len(graph_spec.nodes) > 0

        log.info(f"Loaded graph '{topic}' with {len(graph_spec.nodes)} nodes and {len(graph_spec.edges)} edges")

        # Create output directory
        output_dir = _get_next_output_folder()
        log.info(f"Saving all graph renderings to: {output_dir}")

        # ==================== MERMAID OUTPUTS ====================

        # Orchestration
        orch_mermaid = graphspec_to_orchestration_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "orchestration.mmd").write_text(orch_mermaid, encoding="utf-8")
        orch_html = await render_mermaid_html_async(orch_mermaid, title=f"Orchestration: {topic}")
        (output_dir / "orchestration.html").write_text(orch_html, encoding="utf-8")

        # Dataflow with data
        dataflow_with_data = graphspec_to_dataflow_mermaid_with_data(graph_spec, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "dataflow.mmd").write_text(dataflow_with_data.mermaid_code, encoding="utf-8")
        if dataflow_with_data.stuff_data:
            dataflow_html = await render_mermaid_html_with_data_async(
                dataflow_with_data.mermaid_code,
                stuff_data=dataflow_with_data.stuff_data,
                title=f"Dataflow (Interactive): {topic}",
            )
        else:
            dataflow_html = await render_mermaid_html_async(dataflow_with_data.mermaid_code, title=f"Dataflow: {topic}")
        (output_dir / "dataflow.html").write_text(dataflow_html, encoding="utf-8")

        # Combo with data
        combo_with_data = graphspec_to_combo_mermaid_with_data(graph_spec, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "combo.mmd").write_text(combo_with_data.mermaid_code, encoding="utf-8")
        if combo_with_data.stuff_data:
            combo_html = await render_mermaid_html_with_data_async(
                combo_with_data.mermaid_code,
                stuff_data=combo_with_data.stuff_data,
                title=f"Combo (Interactive): {topic}",
            )
        else:
            combo_html = await render_mermaid_html_async(combo_with_data.mermaid_code, title=f"Combo: {topic}")
        (output_dir / "combo.html").write_text(combo_html, encoding="utf-8")

        # ==================== REACTFLOW OUTPUTS ====================

        # Create ViewSpec and generate ReactFlow HTML
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        # Save ViewSpec JSON
        viewspec_path = output_dir / "viewspec.json"
        viewspec_path.write_text(viewspec.model_dump_json(indent=2), encoding="utf-8")

        # Generate ReactFlow HTML (with embedded GraphSpec for full data)
        reactflow_html = await generate_reactflow_html_async(viewspec, graphspec=graph_spec, title=f"ReactFlow: {topic}")
        reactflow_path = output_dir / "reactflow.html"
        reactflow_path.write_text(reactflow_html, encoding="utf-8")

        # ==================== VERIFICATION ====================

        # Verify all files were created
        expected_files = [
            "orchestration.mmd",
            "orchestration.html",
            "dataflow.mmd",
            "dataflow.html",
            "combo.mmd",
            "combo.html",
            "viewspec.json",
            "reactflow.html",
        ]
        for filename in expected_files:
            file_path = output_dir / filename
            assert file_path.exists(), f"Expected file not created: {file_path}"
            assert file_path.stat().st_size > 0, f"File is empty: {file_path}"

        # Summary
        log.info(
            f"✅ All renderings generated for '{topic}':\n"
            f"  📁 Output: {output_dir}\n"
            f"  📊 Mermaid:\n"
            f"     - orchestration.html\n"
            f"     - dataflow.html\n"
            f"     - combo.html\n"
            f"  🔷 ReactFlow:\n"
            f"     - reactflow.html"
        )
