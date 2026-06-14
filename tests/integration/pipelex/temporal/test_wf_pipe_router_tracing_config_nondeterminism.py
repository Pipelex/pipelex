"""Regression guard for the [TMPRL1100] tracing-config nondeterminism in ``WfPipeRouter``.

The bug: ``wf_pipe_router.py`` reads ``get_config().pipelex.tracing_config`` inside the
workflow body to decide whether to set up tracing — and therefore whether the ``finally``
block schedules ``act_flush_trace_events``. That config is worker-local mutable state, so
activity scheduling is not a pure function of the workflow history. In production this
bites when a workflow recorded by a tracing-enabled worker is replayed by a worker whose
tracing config differs (worker restart, rolling deploy, scale-in): the replay generates a
different command stream and Temporal raises a nondeterminism error.

The ``config-flips`` arm reproduces that scenario in a single process against the
in-process Temporal server — no distributed setup, no frozen history fixture — and
asserts the workflow nevertheless completes. It is RED while the bug is present (TDD):
the workflow fails with ``[TMPRL1100] Nondeterminism error`` instead of completing.

How the reproduction works:

1. Tracing is enabled and a ``trace_context`` is injected on a DRY-mode leaf PipeLLM job,
   so the workflow's first task buffers trace events and ends by scheduling
   ``act_flush_trace_events`` (the only activity a dry leaf workflow schedules).
2. The worker is built with ``max_cached_workflows=0``: the workflow is evicted from the
   cache after every workflow task, so each subsequent task replays the full history from
   scratch — the in-process equivalent of the workflow landing on a *different* worker.
3. ``act_flush_trace_events`` is substituted with a stub that flips
   ``tracing_config.is_enabled`` to ``False`` — the in-process equivalent of "the worker
   that picks up the next workflow task has a different tracing config". Activities run
   in the worker process, so the flip lands between the workflow task that scheduled the
   flush and the one that follows its completion: a deterministic, race-free injection
   point.
4. The post-flush workflow task replays from the start under tracing-off config. With the
   bug, the workflow skips tracing setup, schedules no flush, and tries to complete — but
   the history records an ``act_flush_trace_events`` schedule at that position. Command
   streams diverge; the SDK raises ``workflow.NondeterminismError``.

The ``config-stable`` control arm runs the identical setup with a no-op flush stub that
leaves the config alone: it passes even with the bug present, proving the config flip —
not the forced replays — is what breaks the command stream. Both arms assert from the
fetched history that ``act_flush_trace_events`` was actually scheduled, so neither can
pass vacuously.

``NondeterminismError`` is added to ``workflow_failure_exception_types`` so a divergence
fails the workflow terminally and surfaces in the test. Without it, Temporal's default
turns nondeterminism into a workflow-task failure that retries forever — which is exactly
the production symptom (a silently hung workflow), but useless in a test.
"""

import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from temporalio import activity, workflow
from temporalio.client import Client as TemporalClient
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.act_flush_trace_events import FlushTraceEventsArg, act_flush_trace_events
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.tracing.helpers import act_flush_noop, inject_trace_context, scheduled_activity_names
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

_LEAF_PIPE_CODE = "step_one"
_FLUSH_ACTIVITY_NAME = "act_flush_trace_events"


@activity.defn(name=_FLUSH_ACTIVITY_NAME)
async def _act_flush_flips_worker_tracing_config(arg: FlushTraceEventsArg) -> None:  # noqa: RUF029, ARG001
    """Substitute flush activity simulating a worker whose tracing config differs.

    Flipping the live config here (the activity runs in the worker process) lands the
    change exactly between the workflow task that scheduled this activity and the replay
    triggered by its completion — deterministically reproducing what a rolling deploy or
    config drift does across real workers.
    """
    get_config().pipelex.tracing_config.is_enabled = False


@pytest.fixture
def enable_tracing_restored() -> Generator[None, None, None]:
    """Enable tracing for the test; restore it even though the stub activity flips it.

    Function-scoped on purpose: the ``config-flips`` arm leaves the flag False, and the
    other arm must start from True again.
    """
    tracing_config = get_config().pipelex.tracing_config
    original_enabled = tracing_config.is_enabled
    tracing_config.is_enabled = True
    yield
    tracing_config.is_enabled = original_enabled
    GraphTracerManager.clear_instance()


@pytest.fixture(scope="class")
def leaf_tracing_job() -> Generator[PipeJob, None, None]:
    """DRY-mode PipeJob for a leaf PipeLLM: no inference activity, so the trace flush is
    the only activity the workflow schedules.
    """
    yield from pipe_job_from_bundle(
        bundle_file=SequenceTracingTestData.BUNDLE_FILE,
        pipe_code=_LEAF_PIPE_CODE,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterTracingConfigNondeterminism:
    @pytest.mark.parametrize("worker_config_flips", [False, True], ids=["config-stable", "config-flips"])
    async def test_replay_survives_worker_tracing_config_flip(
        self,
        temporal_client: TemporalClient,
        enable_tracing_restored: None,  # noqa: ARG002 - enables tracing so the workflow schedules the flush
        leaf_tracing_job: PipeJob,
        worker_config_flips: bool,
    ) -> None:
        execution_job = inject_trace_context(leaf_tracing_job, f"tracing_replay_guard_{uuid.uuid4().hex[:12]}")
        flush_substitute = _act_flush_flips_worker_tracing_config if worker_config_flips else act_flush_noop

        # Build the worker directly (not via make_worker) for the two knobs the
        # reproduction needs: cache eviction after every workflow task, and terminal
        # workflow failure on nondeterminism.
        workflows, activities = get_task_manager().workflows_and_activities(
            substitute_activities={act_flush_trace_events: flush_substitute},
        )
        async with Worker(
            temporal_client,
            task_queue=f"q_tracing_replay_guard_{uuid.uuid4().hex[:8]}",
            workflows=workflows,
            activities=activities,
            workflow_runner=UnsandboxedWorkflowRunner(),
            max_cached_workflows=0,
            workflow_failure_exception_types=[workflow.NondeterminismError],
        ) as worker:
            workflow_handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=execution_job,
                id=f"wf_tracing_replay_guard_{uuid.uuid4().hex[:8]}",
                task_queue=worker.task_queue,
                # Safety net: if nondeterminism ever stops being terminal here, the
                # workflow-task retry loop would hang the test forever without this.
                execution_timeout=timedelta(seconds=60),
            )
            # With the bug, the config-flips arm raises WorkflowFailureError here, caused
            # by "[TMPRL1100] Nondeterminism error". Flush scheduling must be a pure
            # function of the workflow payload/history, so the worker-side config flip
            # must not prevent completion.
            pipe_output = await workflow_handle.result()
            assert isinstance(pipe_output, PipeOutput)

            # Guard against a vacuous pass: the recorded history must contain the flush
            # schedule, otherwise there is nothing for a config-divergent replay to
            # diverge on (and the control arm would prove nothing).
            history = await workflow_handle.fetch_history()
            scheduled_names = scheduled_activity_names(history)
            assert _FLUSH_ACTIVITY_NAME in scheduled_names, f"history must record the flush schedule, got: {scheduled_names}"
