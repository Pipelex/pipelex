"""Integration test for the CV batch screening pipeline routed through Temporal.

Validates that a deeply-nested controller stack (PipeSequence -> PipeSequence + PipeBatch ->
PipeSequence -> PipeExtract + PipeLLM) executes correctly when the LibraryCrate ships to
the worker via the PipeJob. Mirrors the pipelex-demos example 21 pipeline.

Runs in dry mode against the in-process Temporal server bundled with the test conftest
(``--temporal-server none``). For live distributed validation, use the
``/temporal-e2e-validate`` skill which dispatches the same bundle through the CLI
against a real Temporal server with split router/runner workers.
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
from tests.integration.pipelex.temporal.test_data import CvBatchScreeningTemporalTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfCvBatchScreening:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(CvBatchScreeningTemporalTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(CvBatchScreeningTemporalTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in CvBatchScreeningTemporalTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_crate_contains_full_pipe_tree(self, cv_batch_screening_job: PipeJob):
        """All controller and operator pipes (outer + nested PipeSequence + batch branch) are in the crate."""
        self._assert_crate_structure(cv_batch_screening_job)

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "PipeBatch dispatching child workflows for the per-CV branch can race under "
            "pytest-xdist when concurrent test classes load overlapping dynamic concepts. "
            "Passes in isolation and via the /temporal-e2e-validate skill in distributed mode."
        ),
    )
    async def test_cv_batch_screening_via_temporal_dry_run(
        self,
        cv_batch_screening_job: PipeJob,
        temporal_client: TemporalClient,
    ):
        """End-to-end dry-run dispatch through WfPipeRouter on an in-process worker.

        Exercises:

        - LibraryCrate propagation to the worker for deeply-nested controllers
        - Dynamic concept hydration for CandidateProfile, JobRequirements, CandidateMatch
        - PipeExtract + PipeLLM operator round-trip through the activity boundary
        - PipeBatch fan-out to per-CV child workflows
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
                arg=cv_batch_screening_job,
                id=workflow_id,
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=60),
            )

        assert isinstance(pipe_output, PipeOutput)
        rehydrate_pipe_output(pipe_output)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in CvBatchScreeningTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
            stuff = working_memory.get_stuff(stuff_name)
            assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"
