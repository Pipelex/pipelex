"""Pin the eviction-safe ``finally`` ordering invariant of ``WfPipeRouter`` (H2 fix).

The invariant: in the workflow's ``finally`` block, ALL synchronous worker-local cleanup
(tracer close, report-delegate event-log context clear, per-run library teardown) runs
BEFORE the awaited ``act_flush_trace_events`` activity. The flush await is a suspension
point where eviction raises a ``BaseException`` (``_WorkflowBeingEvictedError``) that
escapes the ``except Exception`` around the flush and aborts the rest of the ``finally``.
If any cleanup sat after the await, an eviction there would leak state keyed by the
deterministic ``wf_{run_id}`` into the worker-local singletons.

Why eviction and not cancellation: workflow cancellation delivered at an activity await
is converted by the SDK into an ``ActivityError`` (an ``Exception``), which the
best-effort ``except`` around the flush swallows — the workflow then completes normally,
running whatever code follows. Cancellation therefore cannot abort the ``finally`` and
cannot exercise the invariant. Eviction is the real BaseException-at-suspension-point,
and worker shutdown evicts every cached run deterministically.

The reproduction:

1. ``act_flush_trace_events`` is substituted with a stub that signals entry and then
   blocks, parking the workflow exactly at the flush await — by which point the ordering
   invariant says all worker-local cleanup must already have run.
2. The test shuts the worker down (exits the worker context). Shutdown evicts the cached
   run: the workflow coroutine is resumed at the flush await with the eviction
   ``BaseException``, aborting the rest of the ``finally`` — exactly the H2 interruption.
3. The test then asserts the worker-local singletons are clean: no per-run library in
   ``LibraryManager``, no tracer under the run id, no report-delegate event-log context.

A regression that moves any cleanup after the flush await turns these assertions red.
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import ClassVar

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import get_library_manager, get_report_delegate
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.act_flush_trace_events import FlushTraceEventsArg, act_flush_trace_events
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.tracing.helpers import inject_trace_context, scheduled_activity_names
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

_LEAF_PIPE_CODE = "step_one"


class _FlushBlockSignals:
    """Events shared between the test coroutine and the blocking flush stub."""

    entered: ClassVar[asyncio.Event | None] = None
    release: ClassVar[asyncio.Event | None] = None


@activity.defn(name="act_flush_trace_events")
async def _act_flush_blocking(arg: FlushTraceEventsArg) -> None:  # noqa: ARG001
    """Flush substitute that parks the workflow at its flush await."""
    assert _FlushBlockSignals.entered is not None
    assert _FlushBlockSignals.release is not None
    _FlushBlockSignals.entered.set()
    await _FlushBlockSignals.release.wait()


@pytest.fixture(scope="class")
def leaf_tracing_job() -> Generator[PipeJob, None, None]:
    """DRY-mode PipeJob for a leaf PipeLLM: the trace flush is the only activity."""
    yield from pipe_job_from_bundle(
        bundle_file=SequenceTracingTestData.BUNDLE_FILE,
        pipe_code=_LEAF_PIPE_CODE,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterEvictionCleanupOrdering:
    @pytest.fixture(autouse=True)
    def clear_graph_tracer_manager(self) -> Generator[None, None, None]:
        """Reset the process-lifetime tracer singleton so runs cannot leak tracer keys."""
        yield
        GraphTracerManager.clear_instance()

    async def test_eviction_at_flush_await_leaks_no_worker_local_state(
        self,
        temporal_client: TemporalClient,
        leaf_tracing_job: PipeJob,
    ) -> None:
        """Evicting the run while it sits at the flush await must leave the worker-local
        singletons clean: all synchronous cleanup precedes the only await.
        """
        execution_job = inject_trace_context(leaf_tracing_job, f"eviction_ordering_guard_{uuid.uuid4().hex[:12]}")
        assert execution_job.library_crate is not None, "the job must carry a library crate so the workflow opens a per-run library"

        task_queue = f"q_eviction_ordering_{uuid.uuid4().hex[:8]}"
        _FlushBlockSignals.entered = asyncio.Event()
        _FlushBlockSignals.release = asyncio.Event()

        library_manager = get_library_manager()
        tracer_manager = GraphTracerManager.get_or_create_instance()
        report_delegate = get_report_delegate()
        assert isinstance(report_delegate, ReportingManager)

        try:
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                substitute_activities={act_flush_trace_events: _act_flush_blocking},
            ):
                workflow_handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfPipeRouter.run,
                    arg=execution_job,
                    id=f"wf_eviction_ordering_{uuid.uuid4().hex[:8]}",
                    task_queue=task_queue,
                    execution_timeout=timedelta(seconds=60),
                )
                run_id = workflow_handle.first_execution_run_id
                assert run_id is not None

                # The workflow now sits at the flush await — the only await in the
                # finally. Per the ordering invariant, all worker-local cleanup has
                # already run by the time the flush activity starts.
                await asyncio.wait_for(_FlushBlockSignals.entered.wait(), timeout=30)

                # Vacuity guard while the worker is still up: the flush schedule must be
                # in history, proving the workflow is parked at that await.
                history = await workflow_handle.fetch_history()
                assert "act_flush_trace_events" in scheduled_activity_names(history)

                # Exiting the worker context shuts the worker down, which evicts the
                # cached run: the coroutine resumes at the flush await with the eviction
                # BaseException and the rest of the finally is aborted — the H2 shape.

            # Post-eviction: no worker-local state may have leaked. With the bug
            # (cleanup ordered after the flush await), the per-run library, tracer,
            # and event-log context would all still be registered here.
            with pytest.raises(LibraryError):
                library_manager.get_library(library_id=f"wf_{run_id}")
            assert tracer_manager.get_tracer(run_id) is None, "tracer must be closed before the flush await"
            contexts = report_delegate._event_log_contexts  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            assert run_id not in contexts, "event-log context must be cleared before the flush await"

            # Tidy up the abandoned execution (no worker is listening anymore).
            await workflow_handle.terminate(reason="eviction-ordering guard done")
        finally:
            _FlushBlockSignals.release.set()
            _FlushBlockSignals.entered = None
            _FlushBlockSignals.release = None
