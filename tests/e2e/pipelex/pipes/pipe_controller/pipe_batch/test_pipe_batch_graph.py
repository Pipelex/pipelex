"""E2E test for PipeBatch with graph tracing to verify BATCH_ITEM and BATCH_AGGREGATE edges."""

from collections import Counter
from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeSpec
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.tools.misc.file_utils import get_incremental_directory_path, save_text_to_path
from tests.cases import DocumentTestCases
from tests.conftest import TEST_OUTPUTS_DIR
from tests.e2e.pipelex.pipes.pipe_controller.pipe_batch.test_data import JokeBatchGraphExpectations


def _get_next_output_folder() -> Path:
    """Get the next numbered output folder for batch graph outputs."""
    base_dir = Path(TEST_OUTPUTS_DIR) / "pipe_batch_graph"
    return get_incremental_directory_path(base_dir, "run")


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.search
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchGraph:
    """E2E tests for PipeBatch graph generation with batch edges."""

    async def test_pipe_batch_generates_batch_edges(self, pipe_run_mode: PipeRunMode):
        """Test that PipeBatch generates BATCH_ITEM and BATCH_AGGREGATE edges in the graph.

        This test:
        1. Runs a PipeBatch pipeline with graph tracing enabled
        2. Verifies BATCH_ITEM edges are created (list -> item extraction)
        3. Verifies BATCH_AGGREGATE edges are created (items -> output list)
        4. Saves the GraphSpec for inspection
        """
        # Build effective config with graph tracing enabled
        exec_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=True,
            force_include_full_data=False,
        )

        # Run PipeBatch pipeline with graph tracing
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_controller/pipe_batch"],
            pipe_run_mode=pipe_run_mode,
            execution_config=exec_config,
        )
        response = await runner.execute(
            pipe_code="batch_analyze_cvs_for_job_offer",
            inputs={
                "cvs": [
                    DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_CV),
                    DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
                ],
                "job_offer_pdf": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
            },
        )
        pipe_output = response.pipe_output

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

        # Analyze edges by kind
        edges_by_kind: dict[EdgeKind, int] = {}
        for edge in graph_spec.edges:
            edges_by_kind[edge.kind] = edges_by_kind.get(edge.kind, 0) + 1

        log.info(f"Edge counts by kind: {edges_by_kind}")

        # Get batch edges
        batch_item_edges = [edge for edge in graph_spec.edges if edge.kind.is_batch_item]
        batch_aggregate_edges = [edge for edge in graph_spec.edges if edge.kind.is_batch_aggregate]

        log.info(f"BATCH_ITEM edges: {len(batch_item_edges)}")
        for edge in batch_item_edges:
            log.info(f"  {edge.source} --[{edge.label}]--> {edge.target}")

        log.info(f"BATCH_AGGREGATE edges: {len(batch_aggregate_edges)}")
        for edge in batch_aggregate_edges:
            log.info(f"  {edge.source} --[{edge.label}]--> {edge.target}")

        # Verify BATCH_ITEM edges were created
        # We have 2 CVs, and each batch item may be consumed by multiple nodes
        # (e.g., the PipeSequence controller AND its child extract pipe both take cv_pdf as input)
        # So we expect at least 2 BATCH_ITEM edges (one per CV), possibly more if multiple nodes consume each item
        assert len(batch_item_edges) >= 2, (
            f"Expected at least 2 BATCH_ITEM edges (one per CV), got {len(batch_item_edges)}. "
            f"These edges represent list -> item extraction during batch iteration."
        )

        # Verify BATCH_AGGREGATE edges were created (one per branch output)
        # We have 2 CVs, so we expect 2 BATCH_AGGREGATE edges
        assert len(batch_aggregate_edges) >= 2, (
            f"Expected at least 2 BATCH_AGGREGATE edges (one per branch output), got {len(batch_aggregate_edges)}. "
            f"These edges represent items -> output list aggregation."
        )

        # Verify BATCH_ITEM edge labels contain indices
        batch_item_labels = {edge.label for edge in batch_item_edges}
        assert "[0]" in batch_item_labels, "BATCH_ITEM edges should have label [0]"
        assert "[1]" in batch_item_labels, "BATCH_ITEM edges should have label [1]"

        # Verify BATCH_AGGREGATE edge labels contain indices
        batch_aggregate_labels = {edge.label for edge in batch_aggregate_edges}
        assert "[0]" in batch_aggregate_labels, "BATCH_AGGREGATE edges should have label [0]"
        assert "[1]" in batch_aggregate_labels, "BATCH_AGGREGATE edges should have label [1]"

        # Save graph.json for inspection
        output_dir = _get_next_output_folder()
        graph_json_path = output_dir / "graph.json"
        graph_json = graph_spec.to_json()
        save_text_to_path(graph_json, graph_json_path)
        log.info(f"Saved graph.json to: {graph_json_path}")

        # Pretty print the graph summary
        pretty_print(
            {
                "graph_id": graph_spec.graph_id,
                "nodes_count": len(graph_spec.nodes),
                "edges_count": len(graph_spec.edges),
                "edges_by_kind": {str(kind): count for kind, count in edges_by_kind.items()},
                "batch_item_edges": [{"source": edge.source, "target": edge.target, "label": edge.label} for edge in batch_item_edges],
                "batch_aggregate_edges": [{"source": edge.source, "target": edge.target, "label": edge.label} for edge in batch_aggregate_edges],
            },
            title="PipeBatch Graph Summary",
        )

        # Final summary
        log.info(
            f"PipeBatch graph summary:\n"
            f"  - Total nodes: {len(graph_spec.nodes)}\n"
            f"  - Total edges: {len(graph_spec.edges)}\n"
            f"  - BATCH_ITEM edges: {len(batch_item_edges)}\n"
            f"  - BATCH_AGGREGATE edges: {len(batch_aggregate_edges)}\n"
            f"  - Graph saved to: {graph_json_path}"
        )

    async def test_joke_batch_graph_outputs(self, pipe_run_mode: PipeRunMode):
        """Simple test that runs joke_batch.mthds and generates all graph outputs.

        This test runs the joke batch pipeline with graph tracing and generates:
        - graph.json (GraphSpec)
        - mermaidflow.html (Mermaid flowchart)
        - reactflow.html (ReactFlow interactive graph)

        No fancy assertions - just generate the outputs like CLI does.
        """
        # Build config with graph tracing and all graph outputs enabled
        base_config = get_config().pipelex.pipeline_execution_config
        exec_config = base_config.with_execution_overrides(
            generate_graph=True,
            force_include_full_data=False,
        )
        # Enable all graph outputs
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

        # Run joke batch pipeline
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_controller/pipe_batch"],
            pipe_run_mode=pipe_run_mode,
            execution_config=exec_config,
        )
        response = await runner.execute(
            pipe_code="generate_jokes_from_topics",
        )
        pipe_output = response.pipe_output

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.graph_spec is not None

        graph_spec = pipe_output.graph_spec
        log.info(f"Joke batch graph: {len(graph_spec.nodes)} nodes, {len(graph_spec.edges)} edges")

        # Generate all graph outputs like CLI does
        graph_outputs = await generate_graph_outputs(
            graph_spec=graph_spec,
            graph_config=graph_config,
            pipe_code="generate_jokes_from_topics",
        )

        # Save outputs to folder
        output_dir = Path(TEST_OUTPUTS_DIR) / "joke_batch_graph"
        output_dir = get_incremental_directory_path(output_dir, "run")

        if graph_outputs.graphspec_json:
            graph_json_path = output_dir / "graph.json"
            save_text_to_path(graph_outputs.graphspec_json, graph_json_path)
            log.info(f"Saved graph.json to: {graph_json_path}")

        if graph_outputs.mermaidflow_html:
            mermaid_path = output_dir / "mermaidflow.html"
            save_text_to_path(graph_outputs.mermaidflow_html, mermaid_path)
            log.info(f"Saved mermaidflow.html to: {mermaid_path}")

        if graph_outputs.reactflow_html:
            reactflow_path = output_dir / "reactflow.html"
            save_text_to_path(graph_outputs.reactflow_html, reactflow_path)
            log.info(f"Saved reactflow.html to: {reactflow_path}")

        # Log edge counts
        edges_by_kind: dict[str, int] = {}
        for edge in graph_spec.edges:
            kind_str = str(edge.kind)
            edges_by_kind[kind_str] = edges_by_kind.get(kind_str, 0) + 1

        pretty_print(
            {
                "graph_id": graph_spec.graph_id,
                "nodes": len(graph_spec.nodes),
                "edges": len(graph_spec.edges),
                "edges_by_kind": edges_by_kind,
                "output_dir": str(output_dir),
            },
            title="Joke Batch Graph Outputs",
        )

        # ===== Structural validation =====
        # Build node lookup by pipe_code
        nodes_by_id: dict[str, NodeSpec] = {node.node_id: node for node in graph_spec.nodes}
        nodes_by_pipe_code: dict[str, list[NodeSpec]] = {}
        for node in graph_spec.nodes:
            if node.pipe_code:
                nodes_by_pipe_code.setdefault(node.pipe_code, []).append(node)

        # 1. Verify all expected pipe_codes exist
        actual_pipe_codes = set(nodes_by_pipe_code.keys())
        assert actual_pipe_codes == JokeBatchGraphExpectations.EXPECTED_PIPE_CODES, (
            f"Unexpected pipe codes. Expected: {JokeBatchGraphExpectations.EXPECTED_PIPE_CODES}, Got: {actual_pipe_codes}"
        )

        # 2. Verify node counts per pipe_code
        for pipe_code, expected_count in JokeBatchGraphExpectations.EXPECTED_NODE_COUNTS.items():
            actual_count = len(nodes_by_pipe_code.get(pipe_code, []))
            assert actual_count == expected_count, f"Expected {expected_count} nodes for pipe_code '{pipe_code}', got {actual_count}"

        # 3. Verify edge counts by kind
        actual_edge_counts = Counter(str(edge.kind) for edge in graph_spec.edges)
        for kind, expected_count in JokeBatchGraphExpectations.EXPECTED_EDGE_COUNTS.items():
            actual_count = actual_edge_counts.get(kind, 0)
            assert actual_count == expected_count, f"Expected {expected_count} edges of kind '{kind}', got {actual_count}"

        # 4. Verify BATCH_AGGREGATE edges target PipeBatch, not outer PipeSequence
        # Get the PipeBatch node and PipeSequence node
        batch_node = nodes_by_pipe_code["batch_generate_jokes"][0]
        sequence_node = nodes_by_pipe_code["generate_jokes_from_topics"][0]
        branch_nodes = nodes_by_pipe_code["generate_joke"]

        batch_aggregate_edges = [edge for edge in graph_spec.edges if edge.kind.is_batch_aggregate]
        for edge in batch_aggregate_edges:
            # Source should be one of the branch nodes (generate_joke)
            source_node = nodes_by_id.get(edge.source)
            assert source_node is not None, f"Source node {edge.source} not found"
            assert source_node.pipe_code == "generate_joke", f"BATCH_AGGREGATE source should be 'generate_joke', got '{source_node.pipe_code}'"

            # Target should be the PipeBatch node, NOT the outer PipeSequence
            assert edge.target == batch_node.node_id, (
                f"BATCH_AGGREGATE edge should target PipeBatch node '{batch_node.node_id}' "
                f"(pipe_code='batch_generate_jokes'), but targets '{edge.target}'. "
                f"This is a bug if target is the outer PipeSequence '{sequence_node.node_id}'."
            )
            assert edge.target != sequence_node.node_id, "BATCH_AGGREGATE edge should NOT target the outer PipeSequence!"

        # 5. Verify containment edges (branch nodes are inside PipeBatch)
        contains_edges = [edge for edge in graph_spec.edges if edge.kind.is_contains]
        batch_children = {edge.target for edge in contains_edges if edge.source == batch_node.node_id}
        branch_node_ids = {node.node_id for node in branch_nodes}
        assert branch_node_ids.issubset(batch_children), (
            f"Branch nodes {branch_node_ids} should be children of PipeBatch node. Actual PipeBatch children: {batch_children}"
        )

        log.info("Structural validation passed: BATCH_AGGREGATE edges correctly target PipeBatch")

    async def test_article_briefing_dotted_batch_over(self, pipe_run_mode: PipeRunMode):
        """Test that the article_briefing pipeline with dotted-path batch_over runs end-to-end.

        This exercises batch_over="search_result.sources" where sources is a nested
        attribute of the SearchResult stuff, validating the dotted-path resolution
        implemented in SubPipe.run_pipe().
        """
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_controller/pipe_batch"],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="article_briefing",
            inputs={"topic": "artificial intelligence"},
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the synthetic flat name was cleaned up after dotted-path batch processing
        final_memory = pipe_output.working_memory
        assert final_memory.get_optional_stuff("search_result__sources") is None, (
            "Synthetic flat name 'search_result__sources' should be cleaned up after batch processing"
        )

        # Verify the original search_result remains in working memory
        search_result = final_memory.get_optional_stuff("search_result")
        assert search_result is not None, "search_result should remain in working memory after batch processing"

        log.info(f"article_briefing pipeline completed, main_stuff concept: {pipe_output.main_stuff.concept.code}")
