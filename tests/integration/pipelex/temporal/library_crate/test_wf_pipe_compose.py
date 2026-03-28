"""Integration tests for PipeCompose operator through Temporal workflows.

Validates that PipeCompose operators execute on Temporal workers via LibraryCrate propagation.
Also exercises Phase 3 deferred hydration — the Report concept has an inline structure that
requires dynamic class registration on the worker before PipeCompose can construct it.
"""

import uuid
from datetime import timedelta

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.test_data import PipeComposeTemporalTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeCompose:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(PipeComposeTemporalTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(PipeComposeTemporalTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in PipeComposeTemporalTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_crate_contains_compose_pipes(self, compose_job: PipeJob):
        """Verify the crate has all pipe_refs and the Report concept."""
        self._assert_crate_structure(compose_job)
        crate = compose_job.library_crate
        assert crate is not None
        report_ref = f"{PipeComposeTemporalTestData.DOMAIN}.Report"
        assert report_ref in crate.concepts, f"Expected concept_ref '{report_ref}' not found in crate"

    @pytest.mark.xfail(reason="PipeCompose construct dispatches WfMakeJinja2Text which fails to serialize dry-run StuffArtefact")
    async def test_compose_sequence_via_temporal(
        self,
        compose_job: PipeJob,
        temporal_client: TemporalClient,
    ):
        """PipeCompose constructs a structured Report on the worker after deferred hydration."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=compose_job,
                id=workflow_id,
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

        assert isinstance(pipe_output, PipeOutput)
        rehydrate_pipe_output(pipe_output)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in PipeComposeTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"

        # Verify the Report has the expected structured fields (deferred hydration worked)
        report_stuff = working_memory.get_stuff("final_report")
        assert isinstance(report_stuff.content, StructuredContent), (
            f"Expected StructuredContent for final_report, got {type(report_stuff.content).__name__}"
        )
        for field_name in PipeComposeTemporalTestData.EXPECTED_REPORT_FIELDS:
            assert hasattr(report_stuff.content, field_name), f"Report missing field '{field_name}' — deferred hydration may have failed"
