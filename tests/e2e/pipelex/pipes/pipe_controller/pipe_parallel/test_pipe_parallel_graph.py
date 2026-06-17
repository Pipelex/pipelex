"""E2E test for PipeParallel with graph tracing to verify DATA edges from controller to consumers."""

from collections import Counter
from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.graph.graphspec import GraphSpec, NodeSpec
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.tools.misc.file_utils import get_incremental_directory_path, save_text_to_path
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.pipes.pipe_controller.pipe_parallel.test_data import (
    Parallel3BranchGraphExpectations,
    ParallelAddEachGraphExpectations,
    ParallelCombinedGraphExpectations,
    ParallelCombinedGraphExpectationsBase,
)


def _get_next_output_folder(subfolder: str) -> Path:
    """Get the next numbered output folder for parallel graph outputs."""
    base_dir = Path(TEST_OUTPUTS_DIR) / f"pipe_parallel_graph_{subfolder}"
    return get_incremental_directory_path(base_dir, base_name="run")


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelGraph:
    """E2E tests for PipeParallel graph generation with correct DATA edges."""

    async def test_parallel_add_each_output_graph(self, pipe_run_mode: PipeRunMode):
        """Verify PipeParallel with add_each_output generates correct DATA edges.

        This test runs a PipeSequence containing:
        1. PipeParallel (add_each_output=true) that produces short_summary and detailed_summary
        2. A downstream PipeLLM (combine_summaries) that consumes both branch outputs

        Expected: DATA edges flow from PipeParallel to combine_summaries (not from sub-pipes).
        """
        # Build config with graph tracing and all graph outputs enabled
        base_config = get_config().pipelex.pipeline_execution_config
        exec_config = base_config.with_execution_overrides(
            generate_graph=True,
            force_include_full_data=False,
        )
        graph_config = exec_config.graph_config.model_copy(
            update={
                "graphs_inclusion": exec_config.graph_config.graphs_inclusion.model_copy(
                    update={
                        "graphspec_json": True,
                        "mermaidflow_html": True,
                        "reactflow_html": True,
                    }
                )
            }
        )
        exec_config = exec_config.model_copy(update={"graph_config": graph_config})

        # Run pipeline with input text
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_controller/pipe_parallel"],
            pipe_run_mode=pipe_run_mode,
            execution_config=exec_config,
        )
        response = await runner.execute(
            pipe_code="parallel_then_consume",
            inputs={
                "input_text": TextContent(text="The quick brown fox jumps over the lazy dog. This is a sample text for testing parallel processing."),
            },
        )
        pipe_output = response.pipe_output

        # Basic assertions
        assert response.pipe_output is not None
        assert response.pipe_output.working_memory is not None
        assert response.pipe_output.main_stuff is not None

        assert pipe_output.graph_spec is not None
        # Build node lookup
        nodes_by_id: dict[str, NodeSpec] = {node.node_id: node for node in pipe_output.graph_spec.nodes}
        nodes_by_pipe_code: dict[str, list[NodeSpec]] = {}
        for node in pipe_output.graph_spec.nodes:
            if node.pipe_code:
                nodes_by_pipe_code.setdefault(node.pipe_code, []).append(node)

        # 1. Verify all expected pipe_codes exist
        actual_pipe_codes = set(nodes_by_pipe_code.keys())
        assert actual_pipe_codes == ParallelAddEachGraphExpectations.EXPECTED_PIPE_CODES, (
            f"Unexpected pipe codes. Expected: {ParallelAddEachGraphExpectations.EXPECTED_PIPE_CODES}, Got: {actual_pipe_codes}"
        )

        # 2. Verify node counts per pipe_code
        for pipe_code, expected_count in ParallelAddEachGraphExpectations.EXPECTED_NODE_COUNTS.items():
            actual_count = len(nodes_by_pipe_code.get(pipe_code, []))
            assert actual_count == expected_count, f"Expected {expected_count} nodes for pipe_code '{pipe_code}', got {actual_count}"

        # 3. Verify edge counts by kind
        actual_edge_counts = Counter(str(edge.kind) for edge in pipe_output.graph_spec.edges)
        for kind, expected_count in ParallelAddEachGraphExpectations.EXPECTED_EDGE_COUNTS.items():
            actual_count = actual_edge_counts.get(kind, 0)
            assert actual_count == expected_count, f"Expected {expected_count} edges of kind '{kind}', got {actual_count}"

        # 4. Verify DATA edges source from PipeParallel, not from sub-pipes
        parallel_node = nodes_by_pipe_code["parallel_summarize"][0]
        combine_node = nodes_by_pipe_code["combine_summaries"][0]
        data_edges = [edge for edge in pipe_output.graph_spec.edges if edge.kind.is_data]

        for edge in data_edges:
            # DATA edges targeting combine_summaries should come from PipeParallel
            if edge.target == combine_node.node_id:
                assert edge.source == parallel_node.node_id, (
                    f"DATA edge to combine_summaries should come from PipeParallel '{parallel_node.node_id}', "
                    f"but comes from '{edge.source}' (pipe_code: '{nodes_by_id[edge.source].pipe_code}')"
                )

        # 5. Verify PipeParallel node has output specs for both branch outputs
        assert len(parallel_node.node_io.outputs) >= 2, (
            f"PipeParallel should have at least 2 output specs (branch outputs), got {len(parallel_node.node_io.outputs)}"
        )
        output_names = {output.name for output in parallel_node.node_io.outputs}
        assert "short_summary" in output_names, "PipeParallel should have 'short_summary' output"
        assert "detailed_summary" in output_names, "PipeParallel should have 'detailed_summary' output"

        # 6. Verify containment: sub-pipes are inside PipeParallel
        contains_edges = [edge for edge in pipe_output.graph_spec.edges if edge.kind.is_contains]
        parallel_children = {edge.target for edge in contains_edges if edge.source == parallel_node.node_id}
        branch_pipe_codes = {"summarize_short", "summarize_detailed"}
        branch_node_ids = {node.node_id for pipe_code in branch_pipe_codes for node in nodes_by_pipe_code.get(pipe_code, [])}
        assert branch_node_ids.issubset(parallel_children), (
            f"Branch nodes should be children of PipeParallel. Branch IDs: {branch_node_ids}, Parallel children: {parallel_children}"
        )

        # Generate and save graph outputs
        graph_outputs = await generate_graph_outputs(
            graph_spec=pipe_output.graph_spec,
            graph_config=graph_config,
            pipe_code="parallel_then_consume",
        )

        output_dir = _get_next_output_folder("add_each")
        if graph_outputs.graphspec_json:
            save_text_to_path(graph_outputs.graphspec_json, path=output_dir / "graph.json")
        if graph_outputs.mermaidflow_html:
            save_text_to_path(graph_outputs.mermaidflow_html, path=output_dir / "mermaidflow.html")
        if graph_outputs.reactflow_html:
            save_text_to_path(graph_outputs.reactflow_html, path=output_dir / "reactflow.html")

        pretty_print(
            {
                "graph_id": pipe_output.graph_spec.graph_id,
                "nodes": len(pipe_output.graph_spec.nodes),
                "edges": len(pipe_output.graph_spec.edges),
                "edges_by_kind": dict(actual_edge_counts),
                "output_dir": str(output_dir),
            },
            title="Parallel Add Each Graph Outputs",
        )

        log.info("Structural validation passed: DATA edges correctly source from PipeParallel")

    @pytest.mark.parametrize(
        ("pipe_code", "expectations_class"),
        [
            ("pgc_analysis_then_summarize", ParallelCombinedGraphExpectations),
            ("pg3_sequence", Parallel3BranchGraphExpectations),
        ],
    )
    async def test_parallel_combined_output_graph(
        self,
        pipe_run_mode: PipeRunMode,
        pipe_code: str,
        expectations_class: type[ParallelCombinedGraphExpectationsBase],
    ):
        """Verify PipeParallel with combined_output generates correct graph structure.

        Parametrized with:
        - pgc_analysis_then_summarize: 2-branch PipeParallel wrapped in PipeSequence with follow-up consumer
        - pg3_sequence: 3-branch PipeParallel with selective downstream consumption (1 branch unused)
        """
        # Build config with graph tracing
        base_config = get_config().pipelex.pipeline_execution_config
        exec_config = base_config.with_execution_overrides(
            generate_graph=True,
            force_include_full_data=False,
        )
        graph_config = exec_config.graph_config.model_copy(
            update={
                "graphs_inclusion": exec_config.graph_config.graphs_inclusion.model_copy(
                    update={
                        "graphspec_json": True,
                        "reactflow_html": True,
                    }
                )
            }
        )
        exec_config = exec_config.model_copy(update={"graph_config": graph_config})

        # Run pipeline
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_controller/pipe_parallel"],
            pipe_run_mode=pipe_run_mode,
            execution_config=exec_config,
        )
        response = await runner.execute(
            pipe_code=pipe_code,
            inputs={"input_text": TextContent(text="Hello world, this is a test document for parallel analysis.")},
        )
        pipe_output = response.pipe_output

        assert response.pipe_output is not None
        assert response.pipe_output.main_stuff is not None

        # Verify graph
        graph_spec = pipe_output.graph_spec
        assert graph_spec is not None
        assert isinstance(graph_spec, GraphSpec)

        log.info(f"Parallel combined graph ({pipe_code}): {len(graph_spec.nodes)} nodes, {len(graph_spec.edges)} edges")

        # Build node lookup
        nodes_by_pipe_code: dict[str, list[NodeSpec]] = {}
        for node in graph_spec.nodes:
            if node.pipe_code:
                nodes_by_pipe_code.setdefault(node.pipe_code, []).append(node)

        # 1. Verify all expected pipe_codes exist
        actual_pipe_codes = set(nodes_by_pipe_code.keys())
        assert actual_pipe_codes == expectations_class.EXPECTED_PIPE_CODES, (
            f"Unexpected pipe codes. Expected: {expectations_class.EXPECTED_PIPE_CODES}, Got: {actual_pipe_codes}"
        )

        # 2. Verify node counts per pipe_code
        for node_pipe_code, expected_count in expectations_class.EXPECTED_NODE_COUNTS.items():
            actual_count = len(nodes_by_pipe_code.get(node_pipe_code, []))
            assert actual_count == expected_count, f"Expected {expected_count} nodes for pipe_code '{node_pipe_code}', got {actual_count}"

        # 3. Verify edge counts by kind
        actual_edge_counts = Counter(str(edge.kind) for edge in graph_spec.edges)
        for kind, expected_count in expectations_class.EXPECTED_EDGE_COUNTS.items():
            actual_count = actual_edge_counts.get(kind, 0)
            assert actual_count == expected_count, f"Expected {expected_count} edges of kind '{kind}', got {actual_count}"

        # 4. Verify PARALLEL_COMBINE edges connect branch producers to the PipeParallel node
        parallel_pipe_code = expectations_class.PARALLEL_PIPE_CODE
        parallel_node = nodes_by_pipe_code[parallel_pipe_code][0]
        parallel_combine_edges = [edge for edge in graph_spec.edges if edge.kind.is_parallel_combine]
        expected_combine_count = expectations_class.EXPECTED_EDGE_COUNTS.get("parallel_combine", 0)
        assert len(parallel_combine_edges) == expected_combine_count, (
            f"Expected {expected_combine_count} PARALLEL_COMBINE edges, got {len(parallel_combine_edges)}"
        )
        for edge in parallel_combine_edges:
            assert edge.target == parallel_node.node_id, (
                f"PARALLEL_COMBINE edge target should be PipeParallel '{parallel_node.node_id}', got '{edge.target}'"
            )
            assert edge.source_stuff_digest is not None, "PARALLEL_COMBINE edge should have source_stuff_digest"
            assert edge.target_stuff_digest is not None, "PARALLEL_COMBINE edge should have target_stuff_digest"

        # Generate and save graph outputs
        graph_outputs = await generate_graph_outputs(
            graph_spec=graph_spec,
            graph_config=graph_config,
            pipe_code=pipe_code,
        )

        output_dir = _get_next_output_folder(pipe_code)
        if graph_outputs.graphspec_json:
            save_text_to_path(graph_outputs.graphspec_json, path=output_dir / "graph.json")
        if graph_outputs.mermaidflow_html:
            save_text_to_path(graph_outputs.mermaidflow_html, path=output_dir / "mermaidflow.html")
        if graph_outputs.mermaidflow_mmd:
            save_text_to_path(graph_outputs.mermaidflow_mmd, path=output_dir / "mermaidflow.mmd")
        if graph_outputs.reactflow_html:
            save_text_to_path(graph_outputs.reactflow_html, path=output_dir / "reactflow.html")

        pretty_print(
            {
                "graph_id": graph_spec.graph_id,
                "nodes": len(graph_spec.nodes),
                "edges": len(graph_spec.edges),
                "edges_by_kind": dict(actual_edge_counts),
                "parallel_outputs": [output.name for output in parallel_node.node_io.outputs],
                "output_dir": str(output_dir),
            },
            title=f"Parallel Combined Graph Outputs ({pipe_code})",
        )

        log.info(f"Structural validation passed: {pipe_code} combined_output graph is correct")
