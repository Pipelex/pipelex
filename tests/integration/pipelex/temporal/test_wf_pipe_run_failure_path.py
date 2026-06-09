"""Failure-path integration test for ``WfPipeRun``.

Pins the failure-path invariant: when the child ``WfPipeRouter`` raises,
``WfPipeRun`` must still fire ``act_deliver`` with
``status=DeliveryStatus.FAILED`` and an empty ``pipe_output``, then re-raise
the original execution error.

``WfPipeRun`` catches ``ChildWorkflowError`` from
``workflow.execute_child_workflow(...)`` and wraps it as
``WorkflowExecutionError`` in-place; the Worker's
``workflow_failure_exception_types=[WorkflowExecutionError]`` registration is
what makes the re-raise end the workflow terminally instead of triggering
indefinite task-failure retry. This test exercises that path end-to-end
through a real Temporal worker.
"""

import uuid
from collections.abc import Generator

import pytest
from temporalio import activity, workflow
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.test_data import LibraryCrateTestData


@workflow.defn(name="wf_pipe_router")
class WfPipeRouterFailingStub:
    """Stand-in for ``WfPipeRouter`` that always fails.

    Registered with the same ``@workflow.defn`` name so Temporal's dispatcher
    routes ``WfPipeRouter.run`` invocations to this stub on the test worker.
    The real ``WfPipeRouter`` is NOT registered on this worker — that would
    collide on the duplicated Temporal name.
    """

    @workflow.run
    async def run(self, _pipe_job: PipeJob) -> PipeOutput:
        # ``non_retryable=True`` avoids the default Temporal retry loop —
        # otherwise the child workflow retries indefinitely and the test
        # hangs instead of surfacing the failure to ``WfPipeRun.run``.
        msg = "simulated router failure"
        raise ApplicationError(msg, non_retryable=True)


@pytest.fixture(scope="class")
def failure_path_job(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    """A PipeJob built from the simplest available bundle.

    The pipe itself is never invoked — the failing-router stub short-circuits
    before reaching any pipe logic. The PipeJob is required only because
    ``WfPipeRun`` reads ``pipe_job.pipe`` to derive static summary/details
    before dispatching the child workflow.
    """
    yield from pipe_job_from_bundle(
        bundle_file=LibraryCrateTestData.BUNDLE_FILE,
        pipe_code=LibraryCrateTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRunFailurePath:
    async def test_router_failure_fires_delivery_with_failed_status_and_reraises(
        self,
        temporal_client: TemporalClient,
        failure_path_job: PipeJob,
    ) -> None:
        task_queue = f"q_wfrun_fail_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_run_fail_{uuid.uuid4().hex[:8]}"

        # Capture the DeliveryActivityArg for post-run assertion.
        captured_delivery_args: list[DeliveryActivityArg] = []

        @activity.defn(name="act_deliver")
        async def stub_act_deliver(arg: DeliveryActivityArg) -> None:  # noqa: RUF029
            captured_delivery_args.append(arg)

        pipe_run_arg = PipeRunArg(
            pipe_job=failure_path_job,
            delivery_assignment=DeliveryAssignment(),
        ).prepare_for_temporal()

        # Construct the Worker directly: registering ``WfPipeRouterFailingStub``
        # alongside the real ``WfPipeRouter`` (which is registered globally in
        # conftest's boot_temporal) would collide on the ``@workflow.defn``
        # name. Bypassing the global task manager keeps this worker isolated.
        async with Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=[WfPipeRun, WfPipeRouterFailingStub],
            activities=[stub_act_deliver],
            workflow_runner=UnsandboxedWorkflowRunner(),
            # Mirror the production ``make_worker`` config: register
            # ``WorkflowExecutionError`` (the wrapped child failure) and the
            # ``PipelexError`` fail-safe floor as workflow failure types so a
            # workflow re-raising either ends the execution terminally instead
            # of triggering indefinite task-failure retry.
            workflow_failure_exception_types=[WorkflowExecutionError, PipelexError],
        ):
            with pytest.raises(WorkflowFailureError):
                # ``maximum_attempts=1`` disables the workflow-level retry so the
                # WorkflowExecutionError propagates as a single terminal failure.
                # Without it, the default config retry policy retries WfPipeRun
                # indefinitely and the test hangs.
                await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                    workflow=WfPipeRun.run,
                    arg=pipe_run_arg,
                    id=workflow_id,
                    task_queue=task_queue,
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

        assert len(captured_delivery_args) == 1, f"act_deliver should fire exactly once on the failure path, got {len(captured_delivery_args)}"
        delivery_arg = captured_delivery_args[0]
        assert delivery_arg.status == DeliveryStatus.FAILED, (
            f"delivery status should be FAILED when the child router fails, got {delivery_arg.status}"
        )
        assert delivery_arg.pipe_output is None, "pipe_output should be unset when the child router fails (model_copy update only runs on success)"
