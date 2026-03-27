"""Integration tests for deferred WorkingMemory hydration through Temporal workflows.

Validates Phase 3: PipeSequence controllers with dynamic concept classes execute
on Temporal workers. The WorkingMemory is serialized as a raw dict before dispatch,
then hydrated on the worker after load_from_crate() registers the dynamic classes.
"""

import uuid
from collections.abc import Generator

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.test_data import DeferredHydrationTestData


@pytest.fixture(scope="class")
def pipe_job_with_dynamic_concept() -> Generator[PipeJob, None, None]:
    """Build a PipeJob from the dynamic concept test bundle (mthds_content with inline structure)."""
    yield from pipe_job_from_bundle(
        bundle_file=DeferredHydrationTestData.BUNDLE_FILE,
        pipe_code=DeferredHydrationTestData.PIPE_CODE,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfDeferredHydration:
    async def test_crate_contains_dynamic_concept(self, pipe_job_with_dynamic_concept: PipeJob) -> None:
        """The crate should contain the Greeting concept with its structure."""
        crate = pipe_job_with_dynamic_concept.library_crate
        assert crate is not None

        assert len(crate.pipes) == len(DeferredHydrationTestData.EXPECTED_PIPE_REFS)
        for pipe_ref in DeferredHydrationTestData.EXPECTED_PIPE_REFS:
            assert pipe_ref in crate.pipes, f"Expected pipe_ref '{pipe_ref}' not found in crate"

        # Verify the Greeting concept with structure is in the crate
        greeting_ref = f"{DeferredHydrationTestData.DOMAIN}.Greeting"
        assert greeting_ref in crate.concepts, f"Expected concept '{greeting_ref}' not found in crate"

    async def test_dynamic_concept_sequence_via_temporal(
        self,
        pipe_job_with_dynamic_concept: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Full round-trip: dynamic concept classes are registered on the worker via deferred hydration."""
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job_with_dynamic_concept,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in DeferredHydrationTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
            stuff = working_memory.get_stuff(stuff_name)
            assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"

        # Verify greeting_result has StructuredContent with the right fields
        greeting_stuff = working_memory.get_stuff("greeting_result")
        assert isinstance(greeting_stuff.content, StructuredContent), f"Expected StructuredContent, got {type(greeting_stuff.content).__name__}"
        assert hasattr(greeting_stuff.content, "message"), "Greeting content should have 'message' field"
        assert hasattr(greeting_stuff.content, "language"), "Greeting content should have 'language' field"

        # Verify summary_result is TextContent
        summary_stuff = working_memory.get_stuff("summary_result")
        assert isinstance(summary_stuff.content, TextContent)
