"""Integration test: a pipeline run dispatched with a ``request_id`` produces
Temporal workflow log records carrying that id.

Phase 2 of the API-readiness follow-ups wires ``job_metadata.request_id`` into
the worker-side ``WorkflowLog``: ``WfPipeRun`` builds its logger from
``workflow_arg.pipe_job.job_metadata.request_id``, so every record it emits
carries ``request_id`` in its ``extra`` dict. This test pins that end-to-end
wiring against a real Temporal worker.

Modeled on ``test_wf_pipe_run_failure_path.py`` — a failing ``WfPipeRouter``
stub short-circuits before any real pipe execution, so the test exercises
``WfPipeRun``'s logging without needing inference.
"""

import logging
import uuid
from collections.abc import Generator

import pytest
from temporalio import activity, workflow
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from typing_extensions import override

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg
from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.test_data import LibraryCrateTestData

_REQUEST_ID = "r-wf-pipe-run-logging-7f3a"


@workflow.defn(name="wf_pipe_router")
class WfPipeRouterFailingStub:
    """Stand-in for ``WfPipeRouter`` that always fails.

    Registered under the real ``WfPipeRouter``'s Temporal name so ``WfPipeRun``'s
    child-workflow dispatch routes here. Failing immediately short-circuits
    ``WfPipeRun`` past any real pipe execution — the test only needs its logs.
    """

    @workflow.run
    async def run(self, _pipe_job: PipeJob) -> PipeOutput:
        msg = "simulated router failure"
        raise ApplicationError(msg, non_retryable=True)


@pytest.fixture(scope="class")
def request_id_job() -> Generator[PipeJob, None, None]:
    """A PipeJob whose ``job_metadata`` carries a known ``request_id``."""
    for pipe_job in pipe_job_from_bundle(
        bundle_file=LibraryCrateTestData.BUNDLE_FILE,
        pipe_code=LibraryCrateTestData.PIPE_CODE,
        isolated_registry=False,
    ):
        yield pipe_job.model_copy(
            update={"job_metadata": pipe_job.job_metadata.model_copy(update={"request_id": _REQUEST_ID})},
        )


class _RecordingHandler(logging.Handler):
    """Captures every emitted ``LogRecord`` for post-run inspection."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRunRequestIdLogging:
    async def test_dispatched_request_id_rides_on_workflow_log_records(
        self,
        temporal_client: TemporalClient,
        request_id_job: PipeJob,
    ) -> None:
        task_queue = f"q_wfrun_reqid_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_run_reqid_{uuid.uuid4().hex[:8]}"

        @activity.defn(name="act_deliver")
        async def stub_act_deliver(_arg: DeliveryActivityArg) -> None:
            """No-op delivery — the failure path still fires it; its result is irrelevant here."""

        pipe_run_arg = PipeRunArg(
            pipe_job=request_id_job,
            delivery_assignment=DeliveryAssignment(),
        ).prepare_for_temporal()

        # Capture records straight off the Temporal workflow logger: the
        # unsandboxed worker runs workflow code in-process, so its records reach
        # this process's ``temporalio.workflow`` logger. DEBUG level so the
        # opening ``WfPipeRun start`` record is captured alongside the rest.
        temporal_workflow_logger = logging.getLogger("temporalio.workflow")
        handler = _RecordingHandler()
        original_level = temporal_workflow_logger.level
        try:
            temporal_workflow_logger.addHandler(handler)
            temporal_workflow_logger.setLevel(logging.DEBUG)
            async with Worker(
                temporal_client,
                task_queue=task_queue,
                workflows=[WfPipeRun, WfPipeRouterFailingStub],
                activities=[stub_act_deliver],
                workflow_runner=UnsandboxedWorkflowRunner(),
                workflow_failure_exception_types=[WorkflowExecutionError],
            ):
                with pytest.raises(WorkflowFailureError):
                    # ``maximum_attempts=1`` keeps the failure terminal and single — see
                    # test_wf_pipe_run_failure_path.py for why the default retry would hang.
                    await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                        workflow=WfPipeRun.run,
                        arg=pipe_run_arg,
                        id=workflow_id,
                        task_queue=task_queue,
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
        finally:
            temporal_workflow_logger.removeHandler(handler)
            temporal_workflow_logger.setLevel(original_level)

        records_with_request_id = [record for record in handler.records if getattr(record, "request_id", None) == _REQUEST_ID]
        assert records_with_request_id, (
            f"expected WfPipeRun workflow log records carrying request_id={_REQUEST_ID!r}; "
            f"captured {len(handler.records)} record(s), request_ids seen: "
            f"{sorted({str(getattr(record, 'request_id', None)) for record in handler.records})}"
        )
