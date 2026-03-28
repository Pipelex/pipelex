"""Integration tests for combined controller types through Temporal workflows.

Validates that PipeParallel + PipeCondition nested within a single PipeSequence execute
correctly on Temporal workers via LibraryCrate propagation. This exercises the deepest
child workflow dispatch chain: sequence → parallel children → condition child → outcome child.
Also exercises Phase 3 deferred hydration via the QualityReport inline structure concept.
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
from tests.integration.pipelex.temporal.test_data import CombinedPipelineTemporalTestData


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfCombinedPipeline:
    @staticmethod
    def _assert_crate_structure(pipe_job: PipeJob) -> None:
        crate = pipe_job.library_crate
        assert crate is not None, "library_crate should be set on PipeJob"
        assert crate.fingerprint, "fingerprint should be non-empty"

        assert len(crate.pipes) == len(CombinedPipelineTemporalTestData.EXPECTED_PIPE_REFS), (
            f"Expected {len(CombinedPipelineTemporalTestData.EXPECTED_PIPE_REFS)} pipes, got {len(crate.pipes)}"
        )
        for pipe_ref in CombinedPipelineTemporalTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

    async def test_crate_contains_combined_pipes(self, combined_job: PipeJob):
        """Verify the crate has all pipe_refs from parallel, condition, and LLM pipes."""
        self._assert_crate_structure(combined_job)

    @pytest.mark.xfail(reason="PipeCondition expression evaluation dispatches WfMakeJinja2Text which fails to serialize dry-run StuffArtefact")
    async def test_combined_pipeline_via_temporal(
        self,
        combined_job: PipeJob,
        temporal_client: TemporalClient,
    ):
        """Nested parallel + condition dispatch produces a structured QualityReport on the worker."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=combined_job,
                id=workflow_id,
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

        assert isinstance(pipe_output, PipeOutput)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in CombinedPipelineTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"

        # Verify QualityReport has expected structured fields
        report_stuff = working_memory.get_stuff("final_report")
        assert isinstance(report_stuff.content, StructuredContent), (
            f"Expected StructuredContent for final_report, got {type(report_stuff.content).__name__}"
        )
        for field_name in CombinedPipelineTemporalTestData.EXPECTED_REPORT_FIELDS:
            assert hasattr(report_stuff.content, field_name), f"QualityReport missing field '{field_name}' — deferred hydration may have failed"
