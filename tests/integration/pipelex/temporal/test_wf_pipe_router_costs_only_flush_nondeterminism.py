"""Regression guard for the [TMPRL1100] costs-only flush nondeterminism in ``WfPipeRouter``.

The bug (finding H1 in ``wip/distributed-execution/workflow-nondeterminism-audit.md``): in
costs-only tracing mode (``emit_usage_events=True, emit_graph_events=False``) the workflow's
``BufferingEventLog`` is populated exclusively by co-located *activity* completions — the
workflow registers the buffer in the process-global ``ReportingManager`` via ``set_event_log``,
and the activity-side ``report_inference_job`` writes into it from the activity thread. The
workflow's ``finally`` block then gates the ``act_flush_trace_events`` schedule on
``if buffered_events:``, a value that is NOT a pure function of the workflow payload + history.
Live execution drains a non-empty buffer (the co-located activity ran and emitted), so history
records the flush schedule. On replay, activity results come from history without executing,
the freshly recreated buffer stays empty, and no flush command is emitted — the command streams
diverge and Temporal raises ``[TMPRL1100] Nondeterminism error``. In production this fires on a
routine sticky-cache eviction on the SAME worker, no config drift or fleet heterogeneity
required: the silent-hang class.

How the reproduction works:

1. A leaf PipeLLM job runs in LIVE mode with a costs-only trace context. ``act_llm_gen_text``
   is substituted with a stub that synthesizes token usage and reports it through
   ``report_inference_job`` — co-located with the workflow, so the emission takes the
   ReportingManager fast path into the workflow's registered buffer, exactly what a real
   co-located worker does. ``act_flush_trace_events`` is substituted with a no-op so the test
   does not depend on a tracing backend; its *schedule* is what matters.
2. The workflow runs to completion on a normal sticky-cache worker, so the live continuation
   drains a non-empty buffer and schedules the flush. The test asserts from the fetched
   history that the flush was actually scheduled, so it cannot pass vacuously.
3. The recorded history is replayed through ``temporalio.worker.Replayer`` — the exact code
   path a worker takes after a sticky-cache eviction. With the bug, the replay's buffer is
   empty, the flush command is never emitted, and the replay raises a nondeterminism error.
   The test asserts the replay succeeds: RED while the bug is present (TDD).

The ``graph-and-usage`` control arm runs the identical setup with graph events enabled: inline
tracer emissions re-fire deterministically on replay, the buffer is non-empty on both sides,
and the replay succeeds even with the bug present — proving that the costs-only buffer gating,
not the replay harness, is what breaks the command stream.

Fix shape (as landed): activity-side usage events never route through the workflow's
in-sandbox buffer (they take the per-process runner fallback), and the flush schedule is a
pure function of the payload. The payload-pure gate goes further than "always schedule": in
costs-only LIVE mode the buffer is deterministically empty (no graph events, no inline usage
emissions), so the flush activity is skipped entirely — the costs-only arm therefore asserts
the flush is ABSENT from history and that the recorded history still replays cleanly. The
``graph-and-usage`` arm keeps the original vacuity guard (flush present in history).
"""

import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import get_report_delegate
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.act_flush_trace_events import act_flush_trace_events
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.tracing.helpers import (
    act_flush_noop,
    inject_trace_context,
    make_synthetic_usage_llm_job,
    route_activities_to,
    scheduled_activity_names,
)
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

_LEAF_PIPE_CODE = "step_one"
_FLUSH_ACTIVITY_NAME = "act_flush_trace_events"
_FAKE_INFERENCE_MODEL_NAME = "costs_only_replay_fake"
_FAKE_INFERENCE_MODEL_ID = "costs_only_replay_fake_id"
_FAKE_RESPONSE_TEXT = "costs-only replay guard fake response"


@activity.defn(name="act_llm_gen_text")
async def _act_llm_gen_text_reports_usage(llm_assignment: LLMAssignment) -> str:  # noqa: RUF029
    """Substitute for ``act_llm_gen_text`` that emits usage from a CO-LOCATED activity.

    The point is that ``report_inference_job`` runs on the activity thread in the same
    process as the workflow's registered ``BufferingEventLog`` — exactly the co-located
    emission that pre-H1 took the ReportingManager fast path into the workflow's buffer
    (the cross-thread population that replay cannot reproduce). Post-H1 it must take the
    per-process activity event log instead.
    """
    synthetic_job = make_synthetic_usage_llm_job(
        llm_assignment=llm_assignment,
        inference_model_name=_FAKE_INFERENCE_MODEL_NAME,
        inference_model_id=_FAKE_INFERENCE_MODEL_ID,
    )
    get_report_delegate().report_inference_job(inference_job=synthetic_job)
    return _FAKE_RESPONSE_TEXT


@pytest.fixture(scope="class")
def live_leaf_tracing_job() -> Generator[PipeJob, None, None]:
    """LIVE-mode PipeJob for a leaf PipeLLM.

    LIVE pins the arm under test: costs-only LIVE is the shape whose flush schedule
    used to be gated on worker-local buffer content and hung on replay. (Since the
    unified dry run, DRY also dispatches ``act_llm_gen_text`` and emits activity-side,
    but the regression being guarded was recorded against LIVE.)
    """
    yield from pipe_job_from_bundle(
        bundle_file=SequenceTracingTestData.BUNDLE_FILE,
        pipe_code=_LEAF_PIPE_CODE,
        pipe_run_mode=PipeRunMode.LIVE,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterCostsOnlyFlushNondeterminism:
    @pytest.fixture(autouse=True)
    def clear_graph_tracer_manager(self) -> Generator[None, None, None]:
        """Reset the process-lifetime tracer singleton so arms cannot leak tracer keys."""
        yield
        GraphTracerManager.clear_instance()

    @pytest.fixture(scope="class", autouse=True)
    def redirect_traces_dir(self, tmp_path_factory: pytest.TempPathFactory) -> Generator[None, None, None]:
        """Point the NDJSON traces_dir at a temp directory for this class.

        The stub activity's ``report_inference_job`` takes the per-process activity
        event log path, which lazily builds an NDJSON writer in the configured
        traces_dir — without this redirect the test writes stray trace files into the
        repo's default ``.pipelex/traces``.
        """
        ndjson_config = get_config().pipelex.tracing_config.ndjson
        original_dir = ndjson_config.traces_dir if ndjson_config else ""
        if ndjson_config:
            ndjson_config.traces_dir = str(tmp_path_factory.mktemp("traces"))
        yield
        if ndjson_config:
            ndjson_config.traces_dir = original_dir

    @pytest.mark.parametrize("emit_graph_events", [True, False], ids=["graph-and-usage", "costs-only"])
    async def test_recorded_history_replays_deterministically(
        self,
        temporal_client: TemporalClient,
        live_leaf_tracing_job: PipeJob,
        emit_graph_events: bool,
    ) -> None:
        """A history recorded with co-located activity usage emission must replay cleanly.

        With the bug, the ``costs-only`` arm raises a nondeterminism error from
        ``Replayer.replay_workflow``: the flush schedule recorded in history is not
        re-emitted because the replay's buffer is empty. Flush scheduling must be a
        pure function of the workflow payload + history.
        """
        execution_run_id = f"costs_only_replay_guard_{uuid.uuid4().hex[:12]}"
        execution_job = inject_trace_context(
            live_leaf_tracing_job,
            execution_run_id,
            emit_graph_events=emit_graph_events,
            emit_usage_events=True,
        )
        task_queue = f"q_costs_only_replay_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_costs_only_replay_{uuid.uuid4().hex[:8]}"

        with route_activities_to(task_queue, [act_llm_gen_text.__name__]):
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                substitute_activities={
                    act_llm_gen_text: _act_llm_gen_text_reports_usage,
                    act_flush_trace_events: act_flush_noop,
                },
            ):
                workflow_handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfPipeRouter.run,
                    arg=execution_job,
                    id=workflow_id,
                    task_queue=task_queue,
                    # Safety net: a regression that turns the divergence into a
                    # workflow-task retry loop must fail the test, not hang it.
                    execution_timeout=timedelta(seconds=60),
                )
                pipe_output = await workflow_handle.result()
                assert isinstance(pipe_output, PipeOutput)
                history = await workflow_handle.fetch_history()

        scheduled_names = scheduled_activity_names(history)
        if emit_graph_events:
            # Vacuity guard for the replay assertion: the graph arm must record the flush
            # schedule (inline graph events populate the buffer deterministically).
            assert _FLUSH_ACTIVITY_NAME in scheduled_names, f"history must record the flush schedule, got: {scheduled_names}"
        else:
            # Costs-only LIVE: the buffer is deterministically empty (activity-side usage
            # emissions take the per-process runner fallback, never the workflow buffer),
            # so the payload-pure gate skips the guaranteed-empty flush round-trip.
            assert _FLUSH_ACTIVITY_NAME not in scheduled_names, f"costs-only LIVE must skip the empty flush schedule, got: {scheduled_names}"

        # Replay the recorded history — the exact code path of a post-eviction worker.
        # With the bug, the costs-only arm raises here with a nondeterminism error.
        replayer = Replayer(
            workflows=[WfPipeRouter],
            workflow_runner=UnsandboxedWorkflowRunner(),
            data_converter=data_converter,
        )
        await replayer.replay_workflow(history)
