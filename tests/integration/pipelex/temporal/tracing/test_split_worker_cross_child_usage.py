"""Cross-child cost aggregation in split-worker mode.

The fan-out join is by ``pipeline_run_id`` on a shared partition: each child
workflow gets a distinct ``workflow_id`` but the same ``pipeline_run_id``, and
only the top-level run reads the whole partition. No automated test asserts that
usage emitted from *separate child workflows* sums into one parent total — the
existing fan-out tracing tests are graph-only/dry-run, and the sequence
split-worker tests have no child workflows.

This runs the PipeParallel bundle (two branches dispatched as separate child
workflows) in LIVE mode with the runner-side fallback, then asserts the usage
events from multiple workflows aggregate into a single priced total.
"""

import uuid
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.system.configuration.config_temporal import ActivityRouteConfig
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import (
    inject_trace_context,
    make_split_workers,
    ndjson_files_for_run,
)
from tests.integration.pipelex.temporal.tracing.test_data import ParallelTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerCrossChildUsage:
    """Usage from fan-out child workflows aggregates into one parent cost total."""

    @pytest.fixture
    def split_queues(self) -> tuple[str, str]:
        return (f"q_router_{uuid.uuid4().hex[:8]}", f"q_runner_{uuid.uuid4().hex[:8]}")

    @pytest.fixture
    def live_parallel_tracing_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        """The PipeParallel bundle in LIVE mode so branches dispatch ``act_llm_gen_text``.

        LIVE forces the in-workflow activity hop (the runner-side fallback under test); the fake
        ``act_llm_gen_text`` installed by ``make_split_workers`` returns a stub string and
        synthesizes usage, so no real LLM call is made.
        """
        yield from pipe_job_from_bundle(
            bundle_file=ParallelTracingTestData.BUNDLE_FILE,
            pipe_code=ParallelTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
            isolated_registry=is_class_registry_isolated,
        )

    @pytest.fixture
    def route_llm_text_to_runner_queue(self, split_queues: tuple[str, str]) -> Generator[None, None, None]:
        _q_router, q_runner = split_queues
        worker_config = get_config().temporal.worker_config
        activity_name = act_llm_gen_text.__name__
        original_entry = worker_config.activity_queues.get(activity_name)
        worker_config.activity_queues[activity_name] = ActivityRouteConfig(default=q_runner, by_handle={})
        yield
        if original_entry is None:
            worker_config.activity_queues.pop(activity_name, None)
        else:
            worker_config.activity_queues[activity_name] = original_entry

    async def _execute_split(
        self,
        live_parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        split_queues: tuple[str, str],
    ) -> str:
        q_router, q_runner = split_queues
        execution_run_id = f"split_child_{uuid.uuid4().hex[:12]}"
        execution_job = inject_trace_context(live_parallel_tracing_job, execution_run_id)
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        async with make_split_workers(temporal_client, q_router=q_router, q_runner=q_runner):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=execution_job,
                id=workflow_id,
                task_queue=q_router,
            )
        rehydrate_pipe_output(pipe_output)
        return execution_run_id

    async def test_cross_child_usage_aggregates_to_single_parent_total(
        self,
        live_parallel_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
        split_queues: tuple[str, str],
        route_llm_text_to_runner_queue: None,  # noqa: ARG002
    ) -> None:
        """Two branch child workflows + the parent's summarize step each emit usage via the runner
        fallback into the shared ``pipeline_run_id`` partition. Reading the partition once aggregates
        usage across all of them into a single priced total — proving the cross-child fan-out join.
        """
        run_id = await self._execute_split(live_parallel_tracing_job, temporal_client, split_queues)

        # Multiple NDJSON files confirm the branches ran as separate child workflows (parent + children).
        ndjson_files = ndjson_files_for_run(str(tracing_tmp_dir), run_id)
        assert len(ndjson_files) >= 2, f"Expected parent + child-workflow NDJSON files, got {[path.name for path in ndjson_files]}"

        reader = NdjsonEventLog(traces_dir=str(tracing_tmp_dir))
        try:
            events = reader.read_events(run_id)
        finally:
            reader.close()

        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert usage_events, "Expected usage events from the fan-out run"

        # The branches are distinct nodes living in distinct child workflows; their usage must land in
        # the shared partition under more than one workflow_id.
        distinct_workflow_ids = {evt.workflow_id for evt in usage_events}
        distinct_node_ids = {evt.node_id for evt in usage_events}
        assert len(distinct_workflow_ids) >= 2, f"Expected usage across >=2 workflows (cross-child), got {distinct_workflow_ids}"
        assert len(distinct_node_ids) >= 2, f"Expected usage from >=2 distinct nodes, got {distinct_node_ids}"

        tokens_usages = UsageAggregator.aggregate(events)
        expected_total = sum(
            tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0) + tokens_usage.nb_tokens_by_category.get(TokenCategory.OUTPUT, 0)
            for tokens_usage in tokens_usages
        )

        aggregated = CostRegistry.aggregate_costs(tokens_usages=tokens_usages)
        assert aggregated.total_nb_tokens == expected_total
        assert aggregated.total_nb_tokens >= 2 * len(usage_events), "Each runner emit carries at least one input + one output token"
        assert aggregated.has_reportable_usage is True
