"""Integration tests for PipeSequence graph tracing through Temporal workflows.

Validates that a PipeSequence (2 PipeLLM steps) running on a Temporal worker
produces correct NDJSON trace events that assemble into a valid GraphSpec
with CONTAINS and DATA edges.
"""

from pathlib import Path

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeStatus
from pipelex.pipe_run.pipe_job import PipeJob
from tests.integration.pipelex.temporal.tracing.helpers import (
    TracingResult,
    assert_all_nodes_terminal,
    edges_by_kind,
    execute_and_assemble,
    ndjson_files_for_run,
    node_pipe_codes,
)
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfGraphTracingSequence:
    """PipeSequence produces correct GraphSpec via NDJSON event tracing on Temporal."""

    async def _get_result(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ) -> tuple[TracingResult, GraphSpec]:
        """Execute workflow and return result with assembled GraphSpec, asserting it's not None."""
        result = await execute_and_assemble(
            pipe_job=sequence_tracing_job,
            temporal_client=temporal_client,
            traces_dir=str(tracing_tmp_dir),
        )
        assert result.graph_spec is not None, "GraphSpec should be assembled from trace events"
        return result, result.graph_spec

    async def test_sequence_produces_ndjson_files(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Workflow execution writes NDJSON event files to the traces directory."""
        result = await execute_and_assemble(
            pipe_job=sequence_tracing_job,
            temporal_client=temporal_client,
            traces_dir=str(tracing_tmp_dir),
        )
        ndjson_files = ndjson_files_for_run(str(tracing_tmp_dir), result.pipeline_run_id)
        assert len(ndjson_files) >= 1, "At least one NDJSON file should be written"

    async def test_sequence_assembles_valid_graph(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Assembled GraphSpec has expected node count and matching graph_id."""
        result, graph_spec = await self._get_result(sequence_tracing_job, temporal_client, tracing_tmp_dir)
        assert graph_spec.graph_id == result.pipeline_run_id
        assert len(graph_spec.nodes) == SequenceTracingTestData.EXPECTED_NODE_COUNT

    async def test_sequence_all_nodes_succeeded(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """All nodes in the sequence graph have SUCCEEDED status."""
        _result, graph_spec = await self._get_result(sequence_tracing_job, temporal_client, tracing_tmp_dir)
        for node in graph_spec.nodes:
            assert node.status == NodeStatus.SUCCEEDED, f"Node '{node.pipe_code}' should be SUCCEEDED, got {node.status}"
        assert_all_nodes_terminal(graph_spec)

    async def test_sequence_pipe_codes(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """All expected pipe_codes are present in the assembled graph nodes."""
        _result, graph_spec = await self._get_result(sequence_tracing_job, temporal_client, tracing_tmp_dir)
        actual_codes = node_pipe_codes(graph_spec)
        assert actual_codes == SequenceTracingTestData.EXPECTED_PIPE_CODES

    async def test_sequence_contains_edges(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """CONTAINS edges from sequence controller to each child step."""
        _result, graph_spec = await self._get_result(sequence_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        contains_edges = edge_groups.get(EdgeKind.CONTAINS, [])
        assert len(contains_edges) == SequenceTracingTestData.EXPECTED_CONTAINS_EDGE_COUNT

    async def test_sequence_data_edges(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """DATA edges connect step outputs to step inputs."""
        _result, graph_spec = await self._get_result(sequence_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        data_edges = edge_groups.get(EdgeKind.DATA, [])
        assert len(data_edges) >= SequenceTracingTestData.MIN_DATA_EDGES
