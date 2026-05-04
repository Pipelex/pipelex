"""Integration tests for PipeParallel graph tracing through Temporal workflows.

Validates that PipeParallel controllers running as concurrent child workflows
produce correct graph structure in the assembled GraphSpec.
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
from tests.integration.pipelex.temporal.tracing.test_data import ParallelTracingTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfGraphTracingParallel:
    """PipeParallel produces correct graph structure via Temporal tracing."""

    async def _get_result(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ) -> tuple[TracingResult, GraphSpec]:
        """Execute workflow and return result with assembled GraphSpec, asserting it's not None."""
        result = await execute_and_assemble(
            pipe_job=parallel_tracing_job,
            temporal_client=temporal_client,
            traces_dir=str(tracing_tmp_dir),
        )
        assert result.graph_spec is not None, "GraphSpec should be assembled from trace events"
        return result, result.graph_spec

    async def test_parallel_produces_multiple_ndjson_files(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Parallel branches spawn child workflows, producing multiple NDJSON files."""
        result = await execute_and_assemble(
            pipe_job=parallel_tracing_job,
            temporal_client=temporal_client,
            traces_dir=str(tracing_tmp_dir),
        )
        ndjson_files = ndjson_files_for_run(str(tracing_tmp_dir), result.pipeline_run_id)
        # Parent workflow + child workflows (at least 2 for the 2 branches)
        assert len(ndjson_files) >= 2, f"Expected multiple NDJSON files (parent + child workflows), got {len(ndjson_files)}"

    async def test_parallel_all_nodes_succeeded(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """All nodes in the parallel graph are SUCCEEDED."""
        _result, graph_spec = await self._get_result(parallel_tracing_job, temporal_client, tracing_tmp_dir)
        for node in graph_spec.nodes:
            assert node.status == NodeStatus.SUCCEEDED, f"Node '{node.pipe_code}' should be SUCCEEDED, got {node.status}"
        assert_all_nodes_terminal(graph_spec)

    async def test_parallel_pipe_codes(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """All expected pipe_codes are present in the assembled graph."""
        _result, graph_spec = await self._get_result(parallel_tracing_job, temporal_client, tracing_tmp_dir)
        actual_codes = node_pipe_codes(graph_spec)
        assert ParallelTracingTestData.EXPECTED_PIPE_CODES.issubset(actual_codes), (
            f"Missing pipe_codes: {ParallelTracingTestData.EXPECTED_PIPE_CODES - actual_codes}"
        )

    async def test_parallel_node_count(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Graph has at least the minimum expected number of nodes."""
        _result, graph_spec = await self._get_result(parallel_tracing_job, temporal_client, tracing_tmp_dir)
        assert len(graph_spec.nodes) >= ParallelTracingTestData.MIN_NODE_COUNT

    async def test_parallel_contains_edges(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """CONTAINS edges from controllers to their children are present."""
        _result, graph_spec = await self._get_result(parallel_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        contains_edges = edge_groups.get(EdgeKind.CONTAINS, [])
        assert len(contains_edges) >= 2, "At least 2 CONTAINS edges expected (branches inside parallel)"

    async def test_parallel_data_edges(
        self,
        parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """DATA edges connect branch outputs to downstream consumers."""
        _result, graph_spec = await self._get_result(parallel_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        data_edges = edge_groups.get(EdgeKind.DATA, [])
        assert len(data_edges) >= 1, "At least 1 DATA edge expected (branch output → summarize step)"
