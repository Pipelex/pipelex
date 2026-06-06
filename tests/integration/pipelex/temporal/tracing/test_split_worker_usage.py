"""Integration tests for cross-worker UsageReportEvent emission via two task queues.

Validates the Phase 2 runner-side fallback: when `WfPipeRouter` dispatches
`act_llm_gen_text` to a separate task queue (the production deployment topology
where router and runner are physically separated), the runner-side worker —
with no `_event_log_contexts` entry registered for the workflow — emits its
`UsageReportEvent` into the same `traces_dir` partition via the per-process
activity event log, stamped with a stable `act_*` `writer_id`.

`ContentGeneratorInWorkflow.make_llm_text` calls
`workflow.execute_activity(act_llm_gen_text, ..., task_queue=worker_config.resolve_queue(...))`
directly from inside the workflow — there is no child workflow layer
between the router and the activity. The split-worker topology is configured
by overriding `worker_config.activity_queues[act_llm_gen_text].default` to
point at the runner queue.
"""

import uuid
from collections import defaultdict
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.config_temporal import ActivityRouteConfig
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import PipeStartEvent, UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import (
    inject_graph_context,
    make_split_workers,
    ndjson_files_for_run,
)
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerUsageEmission:
    """Cross-process emission: router on q_router, runner on q_runner.

    Each test uses its own pair of task queues (UUID-named) so concurrent
    executions don't share queue state, and resets the per-process activity
    event log cache so the writer_id is regenerated and the warn-once flag
    re-arms for each test.
    """

    @pytest.fixture
    def split_queues(self) -> tuple[str, str]:
        """A fresh (q_router, q_runner) pair per test."""
        return (f"q_router_{uuid.uuid4().hex[:8]}", f"q_runner_{uuid.uuid4().hex[:8]}")

    @pytest.fixture
    def live_sequence_tracing_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        """Like the class-scoped `sequence_tracing_job` but in LIVE mode.

        DRY mode short-circuits the `act_llm_gen_text` activity dispatch
        (`ContentGeneratorDry` reports inline inside the workflow), so the
        cross-worker activity hop never fires. LIVE mode forces the workflow
        to dispatch `act_llm_gen_text` directly via
        `ContentGeneratorInWorkflow.make_llm_text`, which is what the
        runner-side fallback pinned in this suite is supposed to exercise.
        The fake `act_llm_gen_text` substitute installed by
        `make_split_workers` returns a stub string and synthesizes the
        usage report, so no real LLM call is made.
        """
        yield from pipe_job_from_bundle(
            bundle_file=SequenceTracingTestData.BUNDLE_FILE,
            pipe_code=SequenceTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
            isolated_registry=is_class_registry_isolated,
        )

    @pytest.fixture
    def route_llm_text_to_runner_queue(self, split_queues: tuple[str, str]) -> Generator[None, None, None]:
        """Route `act_llm_gen_text` to `q_runner` for the duration of the test.

        Without this override, `ContentGeneratorInWorkflow.make_llm_text` would
        dispatch the activity to whichever task queue the workflow is running on
        (the router queue), defeating the split-worker topology this suite is
        supposed to exercise.
        """
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

    @pytest.fixture(autouse=True)
    def reset_activity_event_log(self) -> Generator[None, None, None]:
        """Clear the per-process activity event log cache between tests.

        The cache (writer_id, event log instance, warn-once flag) is class-level
        on `ActivityEventLogCache`. Without this reset, two tests in the same
        module would share a writer_id and the second test would find a stale,
        possibly closed, event log handle.
        """
        ActivityEventLogCache.reset_for_tests()
        yield
        ActivityEventLogCache.reset_for_tests()

    async def _execute_split(
        self,
        live_sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        split_queues: tuple[str, str],
    ) -> str:
        """Run the workflow on q_router; activities dispatch to q_runner."""
        q_router, q_runner = split_queues
        execution_run_id = f"split_exec_{uuid.uuid4().hex[:12]}"
        execution_job = inject_graph_context(live_sequence_tracing_job, execution_run_id)
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

    async def test_runner_usage_event_lands_in_same_ndjson_dir(
        self,
        live_sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
        split_queues: tuple[str, str],
        route_llm_text_to_runner_queue: None,  # noqa: ARG002
    ) -> None:
        """Router on q_router dispatches inference activity to q_runner.

        The runner — with no `_event_log_contexts` entry — emits its
        `UsageReportEvent` into the same `traces_dir` partition via the
        Phase-2 fallback. Both the router-written `wf_{wf_id}.ndjson`
        (from `act_flush_trace_events`) and at least one runner-written
        `wf_{wf_id}__w_act_*.ndjson` are present.
        """
        run_id = await self._execute_split(live_sequence_tracing_job, temporal_client, split_queues)

        ndjson_files = ndjson_files_for_run(str(tracing_tmp_dir), run_id)
        primary_files = [path for path in ndjson_files if "__w_" not in path.name]
        runner_files = [path for path in ndjson_files if "__w_act_" in path.name]
        assert primary_files, f"Expected a primary wf_*.ndjson router file in {[path.name for path in ndjson_files]}"
        assert runner_files, f"Expected at least one wf_*__w_act_*.ndjson runner file in {[path.name for path in ndjson_files]}"

        reader = NdjsonEventLog(traces_dir=str(tracing_tmp_dir))
        try:
            events = reader.read_events(run_id)
        finally:
            reader.close()

        primary_pipe_starts = [evt for evt in events if isinstance(evt, PipeStartEvent) and evt.writer_id == "primary"]
        runner_usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent) and evt.writer_id.startswith("act_")]
        assert primary_pipe_starts, "Expected at least one PipeStartEvent with writer_id='primary' from the router"
        assert runner_usage_events, "Expected at least one UsageReportEvent with writer_id='act_*' from the runner"

    async def test_no_double_emit_in_split_worker_pool(
        self,
        live_sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
        split_queues: tuple[str, str],
        route_llm_text_to_runner_queue: None,  # noqa: ARG002
    ) -> None:
        """Exactly-once invariant: `_emit_usage_event` takes either the fast
        path OR the fallback path, never both. Submit one workflow; assert
        exactly one `UsageReportEvent` per `(node_id, workflow_id)` across
        all NDJSON files.
        """
        run_id = await self._execute_split(live_sequence_tracing_job, temporal_client, split_queues)

        reader = NdjsonEventLog(traces_dir=str(tracing_tmp_dir))
        try:
            events = reader.read_events(run_id)
        finally:
            reader.close()

        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert usage_events, "Expected at least one UsageReportEvent across the run"

        counts: dict[tuple[str, str], int] = defaultdict(int)
        for usage_event in usage_events:
            counts[usage_event.node_id, usage_event.workflow_id] += 1

        for key, count in counts.items():
            assert count == 1, f"Duplicate UsageReportEvent for (node_id, workflow_id)={key}: count={count}"

    async def test_runner_usage_aggregates_to_tokens_usages(
        self,
        live_sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
        split_queues: tuple[str, str],
        route_llm_text_to_runner_queue: None,  # noqa: ARG002
    ) -> None:
        """The cross-worker usage events feed the production ``UsageAggregator`` (the same path that
        rides ``tokens_usages`` back on PipeOutput): aggregating the read-back stream yields one usage
        record per emitted ``UsageReportEvent``, none dropped.
        """
        run_id = await self._execute_split(live_sequence_tracing_job, temporal_client, split_queues)

        reader = NdjsonEventLog(traces_dir=str(tracing_tmp_dir))
        try:
            events = reader.read_events(run_id)
        finally:
            reader.close()

        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        tokens_usages = UsageAggregator.aggregate(events)
        assert tokens_usages, "Expected the aggregator to surface at least one token-usage record"
        assert len(tokens_usages) == len(usage_events)
        assert tokens_usages == [evt.tokens_usage for evt in usage_events]
