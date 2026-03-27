"""Integration tests for LibraryCrate propagation through Temporal workflows.

Validates Phase 2 of the master plan: PipeSequence controllers execute on Temporal workers
because the LibraryCrate ships inside the PipeJob and gets loaded on the worker.
Uses a bundle with only native Text concepts to avoid the Layer 1 Kajson issue (Phase 3).
"""

import uuid
from datetime import timedelta

import pytest
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowFailureError

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.temporal.test_data import LibraryCrateTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfLibraryCrate:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(LibraryCrateTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(LibraryCrateTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in LibraryCrateTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

        json_str = crate.model_dump_json()
        assert len(json_str) > 0
        roundtripped = crate.model_validate_json(json_str)
        assert roundtripped.fingerprint == crate.fingerprint

    async def _execute_workflow_and_assert(self, pipe_job: PipeJob, temporal_client: TemporalClient) -> None:
        """Execute WfPipeRouter on an inline worker and assert PipeOutput is returned."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in LibraryCrateTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
            stuff = working_memory.get_stuff(stuff_name)
            assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"

    async def test_crate_structure_from_dirs(self, pipe_job_from_library_dirs: PipeJob):
        self._assert_crate_structure(pipe_job_from_library_dirs)

    async def test_crate_structure_from_mthds_content(self, pipe_job_from_mthds_content: PipeJob):
        self._assert_crate_structure(pipe_job_from_mthds_content)

    async def test_pipe_sequence_via_temporal_dry_run(
        self,
        pipe_job_from_library_dirs: PipeJob,
        temporal_client: TemporalClient,
    ):
        """Proves get_required_pipe() works on the worker for child pipes via LibraryCrate."""
        await self._execute_workflow_and_assert(pipe_job_from_library_dirs, temporal_client)

    async def test_pipe_sequence_via_temporal_from_mthds_content(
        self,
        pipe_job_from_mthds_content: PipeJob,
        temporal_client: TemporalClient,
    ):
        """Same as above but the crate was built from an inline mthds_content string."""
        await self._execute_workflow_and_assert(pipe_job_from_mthds_content, temporal_client)

    async def test_missing_crate_fails_pipe_resolution(
        self,
        pipe_job_from_mthds_content: PipeJob,
        temporal_client: TemporalClient,
    ):
        """A PipeJob without a crate should fail: child pipes can't resolve on worker."""
        pipe_job_without_crate = pipe_job_from_mthds_content.model_copy(update={"library_crate": None})

        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            with pytest.raises(WorkflowFailureError):
                await temporal_client.execute_workflow(
                    workflow=WfPipeRouter.run,
                    arg=pipe_job_without_crate,
                    id=workflow_id,
                    task_queue=task_queue,
                    execution_timeout=timedelta(seconds=10),
                )
