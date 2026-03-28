"""Integration tests for PipeCondition dispatch through Temporal workflows.

Validates that PipeCondition controllers execute on Temporal workers via LibraryCrate propagation.
The condition routes to different outcome pipes based on an expression — each outcome is a
child workflow dispatched through PipeRouterChild.
"""

import uuid
from datetime import timedelta

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.temporal.test_data import PipeConditionTemporalTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeCondition:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(PipeConditionTemporalTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(PipeConditionTemporalTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in PipeConditionTemporalTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_crate_contains_condition_pipes(self, condition_job: PipeJob):
        """Verify the crate has all pipe_refs including condition outcomes."""
        self._assert_crate_structure(condition_job)

    @pytest.mark.xfail(reason="PipeCondition expression evaluation dispatches WfMakeJinja2Text which fails to serialize dry-run StuffArtefact")
    async def test_condition_sequence_via_temporal(
        self,
        condition_job: PipeJob,
        temporal_client: TemporalClient,
    ):
        """PipeCondition dispatches the selected outcome as a child workflow on the worker."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=condition_job,
                id=workflow_id,
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

        assert isinstance(pipe_output, PipeOutput)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in PipeConditionTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
            stuff = working_memory.get_stuff(stuff_name)
            assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"
