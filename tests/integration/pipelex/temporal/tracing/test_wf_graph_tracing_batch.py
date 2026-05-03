"""Integration tests for PipeBatch graph tracing through Temporal workflows.

Validates that PipeBatch controllers running as fan-out child workflows
produce BATCH_ITEM and BATCH_AGGREGATE edges in the assembled GraphSpec.
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
)
from tests.integration.pipelex.temporal.tracing.test_data import BatchTracingTestData


# TODO: hangs in CI under pytest-xdist (passes locally and serially); root cause is concurrent
# PipeBatch + WorkflowEnvironment.start_local under load.
@pytest.mark.temporal
@pytest.mark.gha_disabled
@pytest.mark.asyncio(loop_scope="class")
class TestWfGraphTracingBatch:
    """PipeBatch produces BATCH_ITEM and BATCH_AGGREGATE edges in GraphSpec via Temporal tracing."""

    async def _get_result(
        self,
        batch_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ) -> tuple[TracingResult, GraphSpec]:
        """Execute workflow and return result with assembled GraphSpec, asserting it's not None."""
        result = await execute_and_assemble(
            pipe_job=batch_tracing_job,
            temporal_client=temporal_client,
            traces_dir=str(tracing_tmp_dir),
        )
        assert result.graph_spec is not None, "GraphSpec should be assembled from trace events"
        return result, result.graph_spec

    async def test_batch_all_nodes_succeeded(
        self,
        batch_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """All nodes in the batch graph are SUCCEEDED."""
        _result, graph_spec = await self._get_result(batch_tracing_job, temporal_client, tracing_tmp_dir)
        for node in graph_spec.nodes:
            assert node.status == NodeStatus.SUCCEEDED, f"Node '{node.pipe_code}' should be SUCCEEDED, got {node.status}"
        assert_all_nodes_terminal(graph_spec)

    async def test_batch_node_count(
        self,
        batch_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """Graph has at least the minimum expected number of nodes."""
        _result, graph_spec = await self._get_result(batch_tracing_job, temporal_client, tracing_tmp_dir)
        assert len(graph_spec.nodes) >= BatchTracingTestData.MIN_NODE_COUNT

    async def test_batch_item_edges(
        self,
        batch_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """BATCH_ITEM edges present for fan-out from list to item processors."""
        _result, graph_spec = await self._get_result(batch_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        item_edges = edge_groups.get(EdgeKind.BATCH_ITEM, [])
        assert len(item_edges) >= BatchTracingTestData.MIN_BATCH_ITEM_EDGES, (
            f"Expected at least {BatchTracingTestData.MIN_BATCH_ITEM_EDGES} BATCH_ITEM edges, got {len(item_edges)}"
        )

    async def test_batch_aggregate_edges(
        self,
        batch_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
    ):
        """BATCH_AGGREGATE edges present for fan-in from item processors back to controller."""
        _result, graph_spec = await self._get_result(batch_tracing_job, temporal_client, tracing_tmp_dir)
        edge_groups = edges_by_kind(graph_spec)
        aggregate_edges = edge_groups.get(EdgeKind.BATCH_AGGREGATE, [])
        assert len(aggregate_edges) >= BatchTracingTestData.MIN_BATCH_AGGREGATE_EDGES, (
            f"Expected at least {BatchTracingTestData.MIN_BATCH_AGGREGATE_EDGES} BATCH_AGGREGATE edges, got {len(aggregate_edges)}"
        )
