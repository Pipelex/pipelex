"""E2E test for generating all graph renderings from JSON input.

This test loads a GraphSpec from JSON and generates both Mermaid and ReactFlow
outputs in the same folder for easy comparison.
"""

from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec_io import load_graphspec
from pipelex.graph.mermaid import (
    FlowchartDirection,
    collect_stuff_data_html,
    collect_stuff_data_text,
    graphspec_to_combo_mermaid,
    graphspec_to_dataflow_mermaid,
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

        graph_config = self._get_graph_config_with_data()
        pretty_print(graph_config, title="Graph config")

        # ==================== MERMAID OUTPUTS ====================

        # Orchestration
        orch_mermaid = graphspec_to_orchestration_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "orchestration.mmd").write_text(orch_mermaid, encoding="utf-8")
        orch_html = await render_mermaid_html_async(orch_mermaid, title=f"Orchestration: {topic}")
        (output_dir / "orchestration.html").write_text(orch_html, encoding="utf-8")

        # Dataflow with data
        dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "dataflow.mmd").write_text(dataflow_output.mermaid_code, encoding="utf-8")
        has_dataflow_data = dataflow_output.stuff_data or dataflow_output.stuff_data_text or dataflow_output.stuff_data_html
        if has_dataflow_data:
            dataflow_html = await render_mermaid_html_with_data_async(
                dataflow_output.mermaid_code,
                stuff_data=dataflow_output.stuff_data,
                stuff_data_text=dataflow_output.stuff_data_text,
                stuff_data_html=dataflow_output.stuff_data_html,
                stuff_metadata=dataflow_output.stuff_metadata,
                title=f"Dataflow (Interactive): {topic}",
            )
        else:
            dataflow_html = await render_mermaid_html_async(dataflow_output.mermaid_code, title=f"Dataflow: {topic}")
        (output_dir / "dataflow.html").write_text(dataflow_html, encoding="utf-8")

        # Combo with data
        combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        (output_dir / "combo.mmd").write_text(combo_output.mermaid_code, encoding="utf-8")
        has_combo_data = combo_output.stuff_data or combo_output.stuff_data_text or combo_output.stuff_data_html
        if has_combo_data:
            combo_html = await render_mermaid_html_with_data_async(
                combo_output.mermaid_code,
                stuff_data=combo_output.stuff_data,
                stuff_data_text=combo_output.stuff_data_text,
                stuff_data_html=combo_output.stuff_data_html,
                stuff_metadata=combo_output.stuff_metadata,
                title=f"Combo (Interactive): {topic}",
            )
        else:
            combo_html = await render_mermaid_html_async(combo_output.mermaid_code, title=f"Combo: {topic}")
        (output_dir / "combo.html").write_text(combo_html, encoding="utf-8")

        # ==================== REACTFLOW OUTPUTS ====================

        # Create ViewSpec and generate ReactFlow HTML
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        # Save ViewSpec JSON
        viewspec_path = output_dir / "viewspec.json"
        viewspec_path.write_text(viewspec.model_dump_json(indent=2), encoding="utf-8")

        # Collect stuff data in alternate formats if configured
        rf_stuff_data_text: dict[str, str] | None = None
        rf_stuff_data_html: dict[str, str] | None = None
        if graph_config.data_inclusion.stuff_text_content:
            rf_stuff_data_text = collect_stuff_data_text(graph_spec)
        if graph_config.data_inclusion.stuff_html_content:
            rf_stuff_data_html = collect_stuff_data_html(graph_spec)

        # Generate ReactFlow HTML (with embedded GraphSpec for full data)
        reactflow_html = await generate_reactflow_html_async(
            viewspec,
            graphspec=graph_spec,
            stuff_data_text=rf_stuff_data_text,
            stuff_data_html=rf_stuff_data_html,
            title=f"ReactFlow: {topic}",
        )
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

        # Verify stuff data was properly collected when loading from JSON
        # The GraphSpec JSON should have `data` fields, and the collection functions
        # should generate text/html representations from them
        if graph_config.data_inclusion.stuff_json_content:
            # Verify that stuff_data is populated in combo output
            assert combo_output.stuff_data is not None, "stuff_data should be populated when stuff_json_content=True"
            assert len(combo_output.stuff_data) > 0, "stuff_data should not be empty when graph has stuff with data"

        if graph_config.data_inclusion.stuff_text_content:
            # Verify that stuff_data_text is populated (either from data_text or fallback from data)
            assert combo_output.stuff_data_text is not None, "stuff_data_text should be populated when stuff_text_content=True"
            assert len(combo_output.stuff_data_text) > 0, "stuff_data_text should not be empty when graph has stuff with data"

        if graph_config.data_inclusion.stuff_html_content:
            # Verify that stuff_data_html is populated (either from data_html or fallback from data)
            assert combo_output.stuff_data_html is not None, "stuff_data_html should be populated when stuff_html_content=True"
            assert len(combo_output.stuff_data_html) > 0, "stuff_data_html should not be empty when graph has stuff with data"

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
