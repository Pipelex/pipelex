"""E2E test for Mermaid diagram generation from JSON graph input.

This test loads a GraphSpec from JSON and verifies that Mermaid diagrams
and HTML can be generated correctly without requiring inference.
"""

from pathlib import Path

import pytest

from pipelex import log
from pipelex.config import get_config
from pipelex.graph.graphspec_io import load_graphspec
from pipelex.graph.mermaid import (
    FlowchartDirection,
    graphspec_to_combo_mermaid,
    graphspec_to_dataflow_mermaid,
)
from pipelex.graph.mermaid_html import (
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
from pipelex.tools.misc.file_utils import get_incremental_directory_path
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
        """Test generating all Mermaid diagram types from a JSON graph file.

        This test:

        1. Loads a GraphSpec from JSON
        2. Generates dataflow and combo Mermaid diagrams
        3. Renders each to HTML (with interactive data where applicable)
        4. Saves all outputs to TEST_OUTPUTS_DIR
        5. Verifies the structure of generated diagrams and HTML
        """
        # Load graph from JSON
        json_path = Path(graph_json_path)
        assert json_path.exists(), f"Graph JSON file not found: {json_path}"

        graph_spec = load_graphspec(json_path)

        # Verify graph loaded correctly
        assert graph_spec is not None
        assert len(graph_spec.nodes) > 0
        assert len(graph_spec.edges) > 0

        log.info(f"Loaded graph '{topic}' with {len(graph_spec.nodes)} nodes and {len(graph_spec.edges)} edges")

        # Save outputs to TEST_OUTPUTS_DIR
        output_dir = _get_next_output_folder()
        log.info(f"Saving Mermaid outputs to: {output_dir}")

        graph_config = self._get_graph_config_with_data()

        # Generate dataflow Mermaid with data
        dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        assert dataflow_output.mermaid_code.startswith("flowchart TD")

        dataflow_mmd_path = output_dir / "dataflow.mmd"
        dataflow_mmd_path.write_text(dataflow_output.mermaid_code, encoding="utf-8")
        log.info(f"Saved dataflow.mmd: {dataflow_mmd_path}")
        log.info(f"Dataflow stuff_data count: {len(dataflow_output.stuff_data) if dataflow_output.stuff_data else 0}")

        if dataflow_output.stuff_data:
            dataflow_html = await render_mermaid_html_with_data_async(
                dataflow_output.mermaid_code,
                stuff_data=dataflow_output.stuff_data,
                stuff_metadata=dataflow_output.stuff_metadata,
                title=f"Dataflow (Interactive): {topic}",
            )
        else:
            dataflow_html = await render_mermaid_html_async(dataflow_output.mermaid_code, title=f"Dataflow: {topic}")

        dataflow_html_path = output_dir / "dataflow.html"
        dataflow_html_path.write_text(dataflow_html, encoding="utf-8")
        log.info(f"Saved dataflow.html: {dataflow_html_path}")

        # Generate combo Mermaid with data
        combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
        assert combo_output.mermaid_code.startswith("flowchart TD")

        combo_mmd_path = output_dir / "combo.mmd"
        combo_mmd_path.write_text(combo_output.mermaid_code, encoding="utf-8")
        log.info(f"Saved combo.mmd: {combo_mmd_path}")
        log.info(f"Combo stuff_data count: {len(combo_output.stuff_data) if combo_output.stuff_data else 0}")

        if combo_output.stuff_data:
            combo_html = await render_mermaid_html_with_data_async(
                combo_output.mermaid_code,
                stuff_data=combo_output.stuff_data,
                stuff_metadata=combo_output.stuff_metadata,
                title=f"Combo (Interactive): {topic}",
            )
        else:
            combo_html = await render_mermaid_html_async(combo_output.mermaid_code, title=f"Combo: {topic}")

        combo_html_path = output_dir / "combo.html"
        combo_html_path.write_text(combo_html, encoding="utf-8")
        log.info(f"Saved combo.html: {combo_html_path}")

        # Verify all files were saved
        assert dataflow_mmd_path.exists()
        assert dataflow_html_path.exists()
        assert combo_mmd_path.exists()
        assert combo_html_path.exists()

        # Verify HTML structure
        for html_path in [dataflow_html_path, combo_html_path]:
            html_content = html_path.read_text(encoding="utf-8")
            assert html_content.startswith("<!DOCTYPE html>")
            assert "mermaid" in html_content
            assert 'class="mermaid"' in html_content

        log.info(
            f"✅ Mermaid generation complete for '{topic}':\n"
            f"  - Dataflow: {dataflow_mmd_path.stat().st_size} bytes\n"
            f"  - Combo: {combo_mmd_path.stat().st_size} bytes"
        )

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_dataflow_mermaid_structure(self, topic: str, graph_json_path: str) -> None:
        """Test that dataflow Mermaid has correct structure for data-lineage view."""
        _ = topic  # Used for test identification

        graph_spec = load_graphspec(Path(graph_json_path))
        graph_config = self._get_graph_config_with_data()
        dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config)

        mermaid_code = dataflow_output.mermaid_code

        # Verify dataflow-specific structure
        assert "flowchart" in mermaid_code
        assert "classDef pipe" in mermaid_code
        assert "classDef stuff" in mermaid_code

        # Verify stuff_data has expected format (s_xxx keys) if present
        if dataflow_output.stuff_data:
            for stuff_id in dataflow_output.stuff_data:
                assert stuff_id.startswith("s_"), f"Stuff ID should start with 's_': {stuff_id}"

    @pytest.mark.parametrize(
        ("topic", "graph_json_path"),
        GraphTestData.GRAPH_JSON_TEST_CASES,
    )
    async def test_combo_mermaid_structure(self, topic: str, graph_json_path: str) -> None:
        """Test that combo Mermaid combines orchestration and dataflow elements."""
        _ = topic  # Used for test identification

        graph_spec = load_graphspec(Path(graph_json_path))
        graph_config = self._get_graph_config_with_data()
        combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config)

        mermaid_code = combo_output.mermaid_code

        # Verify combo has both orchestration elements (subgraphs) and dataflow elements (stuff)
        assert "flowchart" in mermaid_code
        assert "classDef stuff" in mermaid_code

        # Combo should have subgraphs for controllers
        assert "subgraph" in mermaid_code
