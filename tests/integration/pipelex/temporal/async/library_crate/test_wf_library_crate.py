"""Integration tests for LibraryCrate propagation through Temporal workflows.

Validates Phase 2 of the master plan: PipeSequence controllers execute on Temporal workers
because the LibraryCrate ships inside the PipeJob and gets loaded on the worker.
"""

import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.temporal.test_data import LibraryCrateTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfLibraryCrate:
    """Tests that LibraryCrate ships inside PipeJob and enables pipe resolution on Temporal workers."""

    async def test_crate_structure_from_dirs(self, pipe_job_from_library_dirs: PipeJob):
        """Crate built from library_dirs contains expected pipes and fingerprint."""
        crate = pipe_job_from_library_dirs.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        for pipe_ref in LibraryCrateTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

        # Verify JSON round-trip (structured JSON visibility in Temporal dashboard)
        json_str = crate.model_dump_json()
        assert len(json_str) > 0
        roundtripped = crate.model_validate_json(json_str)
        assert roundtripped.fingerprint == crate.fingerprint

    async def test_crate_structure_from_mthds_content(self, pipe_job_from_mthds_content: PipeJob):
        """Crate built from mthds_content string contains expected pipes and fingerprint."""
        crate = pipe_job_from_mthds_content.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        for pipe_ref in LibraryCrateTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_pipe_sequence_via_temporal_dry_run(
        self,
        pipe_job_from_library_dirs: PipeJob,
        temporal_client: TemporalClient,
    ):
        """PipeSequence executes through WfPipeRouter on an inline Temporal worker (dry run).

        Proves that get_required_pipe() works on the worker for child pipes because the
        LibraryCrate is loaded from the PipeJob into the workflow-scoped library.
        """
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job_from_library_dirs,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        assert pipe_output.working_memory is not None

    async def test_pipe_sequence_via_temporal_from_mthds_content(
        self,
        pipe_job_from_mthds_content: PipeJob,
        temporal_client: TemporalClient,
    ):
        """PipeSequence with crate from mthds_content string executes on Temporal worker (dry run).

        Same as above but the library was loaded from a string (simulating inline bundle content)
        rather than from a directory path. The crate still ships and loads on the worker.
        """
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job_from_mthds_content,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        assert pipe_output.working_memory is not None
