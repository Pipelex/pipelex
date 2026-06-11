"""Regression guard for the cross-run worker-local state collision in ``WfPipeRouter``.

The hazard (priority follow-up of the H2 fix, see
``wip/distributed-execution/nondeterminism-fix-review-follow-ups.md`` item 0): the
per-workflow library, the tracer key, and the report-delegate event-log context are
worker-local singleton entries. If they are keyed by ``workflow.info().workflow_id``,
two *runs* of the same workflow id collide: workflow ids are reused across workflow-level
``retry_policy`` attempts, Temporal reset, and resubmission of the same
``pipeline_run_id`` (``make_workflow_id`` is deterministic). The H2 fix made eviction
reliably execute the ``finally``'s synchronous cleanup — which is destructive cross-run:
a closed predecessor run's late eviction would tear down a live successor run's library,
pop its tracer, and clear its event-log context, failing the successor inline.

The structural fix: key all per-run worker-local state by ``workflow.info().run_id`` —
replay-stable, but unique per run — so cross-run collisions are impossible by
construction. This test pins that keying.

How it works: ``act_llm_gen_text`` is substituted with a stub that blocks on an
``asyncio.Event``, holding the workflow mid-execution with its worker-local state live.
The test then probes the worker-local singletons directly (same process): the library,
tracer, and report-delegate context must exist under run-id-derived keys and must NOT
exist under workflow-id-derived keys. RED while the state is keyed by workflow_id (TDD).
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import ClassVar

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import get_library_manager, get_report_delegate
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.act_flush_trace_events import act_flush_trace_events
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.tracing.helpers import act_flush_noop, inject_trace_context, route_activities_to
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

_LEAF_PIPE_CODE = "step_one"
_FAKE_RESPONSE_TEXT = "run-scoped keying guard fake response"


class _BlockSignals:
    """Events shared between the test coroutine and the blocking activity stub.

    Created fresh by the test on the running loop; class-level so the module-level
    activity stub can reach them.
    """

    entered: ClassVar[asyncio.Event | None] = None
    release: ClassVar[asyncio.Event | None] = None


@activity.defn(name="act_llm_gen_text")
async def _act_llm_gen_text_blocking(llm_assignment: LLMAssignment) -> str:  # noqa: ARG001
    """Substitute for ``act_llm_gen_text`` that parks the workflow mid-execution.

    While this activity is blocked, the workflow's worker-local state (library,
    tracer, report-delegate context) is live and probe-able from the test.
    """
    assert _BlockSignals.entered is not None
    assert _BlockSignals.release is not None
    _BlockSignals.entered.set()
    await _BlockSignals.release.wait()
    return _FAKE_RESPONSE_TEXT


@pytest.fixture(scope="class")
def live_leaf_keying_job() -> Generator[PipeJob, None, None]:
    """LIVE-mode PipeJob for a leaf PipeLLM, carrying a library crate.

    LIVE mode is required so the workflow dispatches ``act_llm_gen_text`` as an
    activity the test can block on (DRY mode short-circuits it inline).
    """
    yield from pipe_job_from_bundle(
        bundle_file=SequenceTracingTestData.BUNDLE_FILE,
        pipe_code=_LEAF_PIPE_CODE,
        pipe_run_mode=PipeRunMode.LIVE,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterRunScopedStateKeying:
    @pytest.fixture(autouse=True)
    def clear_graph_tracer_manager(self) -> Generator[None, None, None]:
        """Reset the process-lifetime tracer singleton so runs cannot leak tracer keys."""
        yield
        GraphTracerManager.clear_instance()

    async def test_worker_local_state_is_keyed_by_run_id_not_workflow_id(
        self,
        temporal_client: TemporalClient,
        live_leaf_keying_job: PipeJob,
    ) -> None:
        """While the workflow is in flight, its worker-local state must live under
        run-id-derived keys, and nothing may be registered under workflow-id keys.
        """
        execution_job = inject_trace_context(
            live_leaf_keying_job,
            f"run_scoped_keying_guard_{uuid.uuid4().hex[:12]}",
            emit_graph_events=False,
            emit_usage_events=True,
        )
        assert execution_job.library_crate is not None, "the job must carry a library crate so the workflow opens a per-run library"

        task_queue = f"q_run_scoped_keying_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_run_scoped_keying_{uuid.uuid4().hex[:8]}"
        _BlockSignals.entered = asyncio.Event()
        _BlockSignals.release = asyncio.Event()

        library_manager = get_library_manager()
        tracer_manager = GraphTracerManager.get_or_create_instance()
        report_delegate = get_report_delegate()
        assert isinstance(report_delegate, ReportingManager)

        try:
            with route_activities_to(task_queue, [act_llm_gen_text.__name__]):
                async with get_task_manager().make_worker(
                    temporal_client,
                    task_queue=task_queue,
                    is_not_sandboxed=True,
                    substitute_activities={
                        act_llm_gen_text: _act_llm_gen_text_blocking,
                        act_flush_trace_events: act_flush_noop,
                    },
                ):
                    workflow_handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                        workflow=WfPipeRouter.run,
                        arg=execution_job,
                        id=workflow_id,
                        task_queue=task_queue,
                        execution_timeout=timedelta(seconds=60),
                    )
                    run_id = workflow_handle.first_execution_run_id
                    assert run_id is not None

                    await asyncio.wait_for(_BlockSignals.entered.wait(), timeout=30)

                    # Library: present under wf_{run_id}, absent under wf_{workflow_id}.
                    library_manager.get_library(library_id=f"wf_{run_id}")
                    with pytest.raises(LibraryError):
                        library_manager.get_library(library_id=f"wf_{workflow_id}")

                    # Tracer: registered under run_id, not workflow_id.
                    assert tracer_manager.get_tracer(run_id) is not None, "tracer must be keyed by run_id"
                    assert tracer_manager.get_tracer(workflow_id) is None, "tracer must not be keyed by workflow_id"

                    # Report-delegate event-log context: keyed by run_id, not workflow_id.
                    contexts = report_delegate._event_log_contexts  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                    assert run_id in contexts, "event-log context must be keyed by run_id"
                    assert workflow_id not in contexts, "event-log context must not be keyed by workflow_id"

                    _BlockSignals.release.set()
                    pipe_output = await workflow_handle.result()
                    assert isinstance(pipe_output, PipeOutput)

                    # After completion, the run-scoped state must be fully cleaned up.
                    with pytest.raises(LibraryError):
                        library_manager.get_library(library_id=f"wf_{run_id}")
                    assert tracer_manager.get_tracer(run_id) is None
                    assert run_id not in contexts
        finally:
            _BlockSignals.entered = None
            _BlockSignals.release = None
