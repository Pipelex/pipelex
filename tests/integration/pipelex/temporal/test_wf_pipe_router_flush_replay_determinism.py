"""Regression guard: WfPipeRouter must replay deterministically regardless of the
worker's local tracing config.

Background — the deployed TMPRL1100 incident:
    wf_pipe_router.py used to read ``get_config().pipelex.tracing_config.is_enabled``
    inside the workflow body to decide whether to schedule ``act_flush_trace_events``.
    That config is worker-local and mutable (it differs across pods, across a rolling
    deploy, and across pipelex versions). Workflow code must be a pure function of its
    history; reading mutable worker config to gate activity scheduling is not. When a
    worker whose tracing config differed from the one that wrote the history replayed
    the workflow, the command stream diverged and Temporal raised
    ``[TMPRL1100] Nondeterminism error``. The fix gates the tracing block solely on the
    durable, payload-carried ``trace_context``; the worker-local "tracing off" preference
    is honored at the activity level instead (``flush_trace_events_to_backend`` no-ops).

This test replays a real recorded history — a leaf PipeLLM workflow whose history is
``[act_llm_gen_object, act_flush_trace_events]``, recorded with tracing ENABLED — under
BOTH worker tracing configs. Both must replay clean. Before the fix, the
``is_enabled = False`` arm raised a NondeterminismError on the ``act_flush_trace_events``
schedule (the replaying worker, seeing tracing off, did not re-schedule the flush the
history records).

The Replayer runs fully in-process — no Temporal server — so this guard is immune to the
``WorkflowEnvironment.start_local`` flakiness that disables the ``tracing/`` suite in CI.

To regenerate the fixture: run any traced PipeLLM workflow through Temporal with
``tracing_config.is_enabled = True`` and dump a leaf child's history via
``temporal workflow show --workflow-id <leaf-id> -o json``.
"""

from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner

from pipelex.config import get_config
from pipelex.temporal.temporal_data_converter import data_converter
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun

_FIXTURE = Path(__file__).parent / "replay_fixtures" / "leaf_pipellm_tracing_on_history.json"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterFlushReplayDeterminism:
    @pytest.mark.parametrize("worker_tracing_enabled", [True, False], ids=["tracing-on", "tracing-off"])
    async def test_flush_scheduling_is_independent_of_worker_tracing_config(self, worker_tracing_enabled: bool) -> None:
        history = WorkflowHistory.from_json("replay-determinism-guard", _FIXTURE.read_text(encoding="utf-8"))

        # Sanity: the recorded history must contain the flush activity, otherwise this
        # guard would pass vacuously (nothing for tracing-off replay to diverge on).
        scheduled = [
            event.activity_task_scheduled_event_attributes.activity_type.name
            for event in history.events
            if event.HasField("activity_task_scheduled_event_attributes")
        ]
        assert "act_flush_trace_events" in scheduled, "fixture must record act_flush_trace_events"

        tracing_config = get_config().pipelex.tracing_config
        original_enabled = tracing_config.is_enabled
        tracing_config.is_enabled = worker_tracing_enabled
        try:
            replayer = Replayer(
                workflows=[WfPipeRouter, WfPipeRun],
                data_converter=data_converter,
                workflow_runner=UnsandboxedWorkflowRunner(),
            )
            # Raises on any replay failure (default raise_on_replay_failure=True). A
            # reintroduced get_config() read in the workflow body would surface here as
            # [TMPRL1100] Nondeterminism error on the tracing-off arm.
            await replayer.replay_workflow(history)
        finally:
            tracing_config.is_enabled = original_enabled
