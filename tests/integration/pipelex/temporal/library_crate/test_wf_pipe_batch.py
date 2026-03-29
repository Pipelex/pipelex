"""Integration tests for PipeBatch dispatch through Temporal workflows.

Validates that PipeBatch controllers execute on Temporal workers via LibraryCrate propagation.
Each batch item is dispatched as a separate child workflow through PipeRouterChild (fan-out).
"""

import uuid
from datetime import timedelta

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.test_data import PipeBatchTemporalTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeBatch:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(PipeBatchTemporalTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(PipeBatchTemporalTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in PipeBatchTemporalTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_crate_contains_batch_pipes(self, batch_job: PipeJob):
        """Verify the crate has all pipe_refs including the batch branch pipe."""
        self._assert_crate_structure(batch_job)

    @pytest.mark.xfail(reason="ListContent deferred hydration fails: list container deserialized as single Topic instead of ListContent[Topic]")
    async def test_batch_sequence_via_temporal(
        self,
        batch_job: PipeJob,
        temporal_client: TemporalClient,
    ):
        """PipeBatch dispatches one child workflow per list item (fan-out) on the worker."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=batch_job,
                id=workflow_id,
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

        assert isinstance(pipe_output, PipeOutput)
        rehydrate_pipe_output(pipe_output)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in PipeBatchTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
            stuff = working_memory.get_stuff(stuff_name)
            assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"
