"""E2E test for execution graph generation with full data capture.

This test runs a pipeline with graph tracing and full data capture,
then verifies the data is correctly stored and can be rendered to
interactive Mermaid diagrams.
"""

from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.core.stuffs.pdf_content import PDFContent
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.graphspec_io import save_graphspec
from pipelex.graph.mermaid import (
    FlowchartDirection,
    graphspec_to_combo_mermaid,
    graphspec_to_dataflow_mermaid,
    graphspec_to_orchestration_mermaid,
)
from pipelex.graph.reactflow_html import generate_reactflow_html_async
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.mermaid_utils import (
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
from tests.cases import PDFTestCases
from tests.conftest import TEST_OUTPUTS_DIR


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder in TEST_OUTPUTS_DIR.

    Creates folders like: temp/test_outputs/graph_full_data/run_01, run_02, etc.
    """
    base_dir = str(Path(TEST_OUTPUTS_DIR) / "graph_full_data")
    return Path(get_incremental_directory_path(base_dir, "run"))


async def _save_graph_outputs(graph_spec: GraphSpec, output_dir: Path) -> dict[str, int]:
    """Save all graph outputs and return stats about stuff_data collection."""
    # Get graph config with ALL stuff data formats enabled for interactive rendering
    base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
    new_data_inclusion = base_graph_config.data_inclusion.model_copy(
        update={
            "stuff_json_content": True,
            "stuff_text_content": True,
            "stuff_html_content": True,
        }
    )
    graph_config = base_graph_config.model_copy(update={"data_inclusion": new_data_inclusion})

    # Save graph.json
    graph_json_path = output_dir / "graph.json"
    save_graphspec(graph_spec, graph_json_path)
    log.info(f"Saved graph.json to: {graph_json_path}")

    # Generate and save mermaid files
    # Orchestration
    orch_mermaid = graphspec_to_orchestration_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
    (output_dir / "orchestration.mmd").write_text(orch_mermaid, encoding="utf-8")
    orch_html = await render_mermaid_html_async(orch_mermaid, title="Orchestration")
    (output_dir / "orchestration.html").write_text(orch_html, encoding="utf-8")

    # Dataflow with data
    dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
    (output_dir / "dataflow.mmd").write_text(dataflow_output.mermaid_code, encoding="utf-8")

    log.info(f"Dataflow stuff_data keys: {list(dataflow_output.stuff_data.keys()) if dataflow_output.stuff_data else []}")
    pretty_print(dataflow_output.stuff_data, title="Dataflow stuff_data")

    has_dataflow_data = dataflow_output.stuff_data or dataflow_output.stuff_data_text or dataflow_output.stuff_data_html
    if has_dataflow_data:
        dataflow_html = await render_mermaid_html_with_data_async(
            dataflow_output.mermaid_code,
            stuff_data=dataflow_output.stuff_data,
            stuff_data_text=dataflow_output.stuff_data_text,
            stuff_data_html=dataflow_output.stuff_data_html,
            title="Dataflow (Interactive)",
        )
    else:
        dataflow_html = await render_mermaid_html_async(dataflow_output.mermaid_code, title="Dataflow")
    (output_dir / "dataflow.html").write_text(dataflow_html, encoding="utf-8")

    # Combo with data
    combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=FlowchartDirection.TOP_DOWN)
    (output_dir / "combo.mmd").write_text(combo_output.mermaid_code, encoding="utf-8")

    log.info(f"Combo stuff_data keys: {list(combo_output.stuff_data.keys()) if combo_output.stuff_data else []}")

    has_combo_data = combo_output.stuff_data or combo_output.stuff_data_text or combo_output.stuff_data_html
    if has_combo_data:
        combo_html = await render_mermaid_html_with_data_async(
            combo_output.mermaid_code,
            stuff_data=combo_output.stuff_data,
            stuff_data_text=combo_output.stuff_data_text,
            stuff_data_html=combo_output.stuff_data_html,
            title="Combo (Interactive)",
        )
    else:
        combo_html = await render_mermaid_html_async(combo_output.mermaid_code, title="Combo")
    (output_dir / "combo.html").write_text(combo_html, encoding="utf-8")

    log.info(f"✅ All graph outputs saved to: {output_dir}")

    return {
        "dataflow_stuff_data_count": len(dataflow_output.stuff_data) if dataflow_output.stuff_data else 0,
        "combo_stuff_data_count": len(combo_output.stuff_data) if combo_output.stuff_data else 0,
    }


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestGraphWithFullData:
    """E2E tests for graph generation with full data capture."""

    async def test_graph_captures_full_data(self, pipe_run_mode: PipeRunMode):
        """Test that running a pipeline with graph tracing captures full I/O data.

        This test:

        1. Runs a pipeline with generate_graph=True and include_full_data=True
        2. Verifies the graph_spec is populated with data in IOSpec fields
        3. Saves all outputs (graph.json, mermaid, HTML) to a numbered folder
        4. Verifies interactive rendering works with the captured data
        """
        # Build effective config with graph tracing and full data capture enabled
        exec_config = get_config().pipelex.pipeline_execution_config.with_graph_overrides(
            generate_graph=True,
            include_full_data=True,
        )

        # Run pipeline with graph tracing and full data capture
        pipe_output = await execute_pipeline(
            pipe_code="cv_job_matcher",
            library_dirs=["tests/e2e/pipelex/pipes/pipe_operators/pipe_compose"],
            inputs={
                "cv_pdf": PDFContent(url=PDFTestCases.PDF_FILE_PATH_CV),
                "job_offer_pdf": PDFContent(url=PDFTestCases.PDF_FILE_PATH_2),
            },
            pipe_run_mode=pipe_run_mode,
            execution_config=exec_config,
        )

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify graph was generated
        graph_spec = pipe_output.graph_spec
        assert graph_spec is not None, "GraphSpec should be populated when generate_graph=True"
        assert isinstance(graph_spec, GraphSpec)
        assert len(graph_spec.nodes) > 0, "Graph should have nodes"
        assert len(graph_spec.edges) > 0, "Graph should have edges"

        log.info(f"Graph generated with {len(graph_spec.nodes)} nodes and {len(graph_spec.edges)} edges")

        # Count nodes and their data presence (all three formats: json, text, html)
        total_inputs = 0
        total_outputs = 0
        inputs_with_data = 0
        outputs_with_data = 0
        inputs_with_data_text = 0
        outputs_with_data_text = 0
        inputs_with_data_html = 0
        outputs_with_data_html = 0
        nodes_missing_input_data: list[str] = []
        nodes_missing_output_data: list[str] = []

        for node in graph_spec.nodes:
            node_inputs_with_data = 0
            node_outputs_with_data = 0

            for input_spec in node.node_io.inputs:
                total_inputs += 1
                if input_spec.data is not None:
                    inputs_with_data += 1
                    node_inputs_with_data += 1
                    log.verbose(f"Node {node.pipe_code}: input '{input_spec.name}' has data")
                else:
                    log.warning(f"Node {node.pipe_code}: input '{input_spec.name}' is MISSING data")
                if input_spec.data_text is not None:
                    inputs_with_data_text += 1
                    log.verbose(f"Node {node.pipe_code}: input '{input_spec.name}' has data_text ({len(input_spec.data_text)} chars)")
                else:
                    log.warning(f"Node {node.pipe_code}: input '{input_spec.name}' is MISSING data_text")
                if input_spec.data_html is not None:
                    inputs_with_data_html += 1
                    log.verbose(f"Node {node.pipe_code}: input '{input_spec.name}' has data_html ({len(input_spec.data_html)} chars)")
                else:
                    log.warning(f"Node {node.pipe_code}: input '{input_spec.name}' is MISSING data_html")

            for output_spec in node.node_io.outputs:
                total_outputs += 1
                if output_spec.data is not None:
                    outputs_with_data += 1
                    node_outputs_with_data += 1
                    log.verbose(f"Node {node.pipe_code}: output '{output_spec.name}' has data")
                else:
                    log.warning(f"Node {node.pipe_code}: output '{output_spec.name}' is MISSING data")
                if output_spec.data_text is not None:
                    outputs_with_data_text += 1
                    log.verbose(f"Node {node.pipe_code}: output '{output_spec.name}' has data_text ({len(output_spec.data_text)} chars)")
                else:
                    log.warning(f"Node {node.pipe_code}: output '{output_spec.name}' is MISSING data_text")
                if output_spec.data_html is not None:
                    outputs_with_data_html += 1
                    log.verbose(f"Node {node.pipe_code}: output '{output_spec.name}' has data_html ({len(output_spec.data_html)} chars)")
                else:
                    log.warning(f"Node {node.pipe_code}: output '{output_spec.name}' is MISSING data_html")

            # Track nodes missing data (only if they have inputs/outputs)
            node_display_name = node.pipe_code or node.node_id
            if len(node.node_io.inputs) > 0 and node_inputs_with_data == 0:
                nodes_missing_input_data.append(node_display_name)
            if len(node.node_io.outputs) > 0 and node_outputs_with_data == 0:
                nodes_missing_output_data.append(node_display_name)

        log.info(f"Found {inputs_with_data}/{total_inputs} inputs with data, {outputs_with_data}/{total_outputs} outputs with data")
        log.info(
            f"Found {inputs_with_data_text}/{total_inputs} inputs with data_text, {outputs_with_data_text}/{total_outputs} outputs with data_text"
        )
        log.info(
            f"Found {inputs_with_data_html}/{total_inputs} inputs with data_html, {outputs_with_data_html}/{total_outputs} outputs with data_html"
        )

        # CRITICAL: All nodes with inputs should have data on ALL their inputs
        assert inputs_with_data == total_inputs, (
            f"All inputs should have data when include_full_data=True. "
            f"Got {inputs_with_data}/{total_inputs} inputs with data. "
            f"Nodes missing input data: {nodes_missing_input_data}"
        )

        # CRITICAL: All nodes with outputs should have data on ALL their outputs
        assert outputs_with_data == total_outputs, (
            f"All outputs should have data when include_full_data=True. "
            f"Got {outputs_with_data}/{total_outputs} outputs with data. "
            f"Nodes missing output data: {nodes_missing_output_data}"
        )

        # CRITICAL: All nodes with inputs should have data_text on ALL their inputs
        assert inputs_with_data_text == total_inputs, (
            f"All inputs should have data_text when include_full_data=True. Got {inputs_with_data_text}/{total_inputs} inputs with data_text."
        )

        # CRITICAL: All nodes with outputs should have data_text on ALL their outputs
        assert outputs_with_data_text == total_outputs, (
            f"All outputs should have data_text when include_full_data=True. Got {outputs_with_data_text}/{total_outputs} outputs with data_text."
        )

        # CRITICAL: All nodes with inputs should have data_html on ALL their inputs
        assert inputs_with_data_html == total_inputs, (
            f"All inputs should have data_html when include_full_data=True. Got {inputs_with_data_html}/{total_inputs} inputs with data_html."
        )

        # CRITICAL: All nodes with outputs should have data_html on ALL their outputs
        assert outputs_with_data_html == total_outputs, (
            f"All outputs should have data_html when include_full_data=True. Got {outputs_with_data_html}/{total_outputs} outputs with data_html."
        )

        # Save all outputs to numbered folder
        output_dir = _get_next_output_folder()
        log.info(f"Saving graph outputs to: {output_dir}")

        stats = await _save_graph_outputs(graph_spec, output_dir)

        # Verify stuff_data was collected
        assert stats["dataflow_stuff_data_count"] > 0, (
            f"Dataflow should have stuff_data extracted from graph. Graph has {inputs_with_data} inputs and {outputs_with_data} outputs with data."
        )

        # Generate ReactFlow HTML
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)
        reactflow_html = await generate_reactflow_html_async(viewspec, graphspec=graph_spec, title="Graph: cv_job_matcher")
        reactflow_path = output_dir / "combo.reactflow.html"
        reactflow_path.write_text(reactflow_html, encoding="utf-8")
        log.info(f"Saved ReactFlow HTML to: {reactflow_path}")

        # Verify ReactFlow HTML structure
        assert reactflow_path.exists()
        assert reactflow_path.stat().st_size > 0
        html_content = reactflow_path.read_text(encoding="utf-8")
        assert '<script type="application/json" id="pipelex-viewspec">' in html_content
        assert '<script type="application/json" id="pipelex-graphspec">' in html_content
        assert "ReactFlow" in html_content
        assert "getLayoutedElements" in html_content
        assert f'"{graph_spec.graph_id}"' in html_content  # ViewSpec should contain graph_id

        # Final summary
        log.info(
            f"Graph summary:\n"
            f"  - Nodes: {len(graph_spec.nodes)}\n"
            f"  - Edges: {len(graph_spec.edges)}\n"
            f"  - Inputs with data: {inputs_with_data}/{total_inputs}\n"
            f"  - Outputs with data: {outputs_with_data}/{total_outputs}\n"
            f"  - Dataflow stuff_data entries: {stats['dataflow_stuff_data_count']}\n"
            f"  - Combo stuff_data entries: {stats['combo_stuff_data_count']}\n"
            f"  - ReactFlow HTML: {reactflow_path.stat().st_size} bytes"
        )
