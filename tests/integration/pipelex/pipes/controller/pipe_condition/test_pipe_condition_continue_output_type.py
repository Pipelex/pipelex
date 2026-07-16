"""Integration test for PipeCondition with continue outcome in a batch context.

Tests that when batching over VerifiedLinks, the PipeCondition correctly:
- Creates Constraints for approved links
- Resolves absent (continue) for rejected links, which the batch compacts away (D4)

Live: the rejected link's branch resolves absent and is dropped from the aggregated list.
Dry: the dry sweep runs every mapped outcome (the builder pipe), so every item yields a mock
constraint — the continue arm is modeled statically (Step D), not by the dry run.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.controller.pipe_condition.pipe_condition_continue_output_type import (
    Constraint,
    VerifiedLink,
)


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionContinueOutputType:
    """Test PipeCondition with continue outcome when batching over verified links."""

    async def test_batch_with_mixed_verdicts(
        self,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
        pipe_run_mode: PipeRunMode,
    ):
        """Test batching over VerifiedLinks with mixed verdicts.

        Given 2 VerifiedLinks:
        - One approved (creates a Constraint)
        - One rejected (resolves absent via 'continue' and is compacted away — live only)
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])

        # Create two VerifiedLinks - one approved, one rejected
        approved_link = VerifiedLink(
            source="EventA",
            target="EventB",
            verdict="approved",
        )
        rejected_link = VerifiedLink(
            source="EventC",
            target="EventD",
            verdict="rejected",
        )

        # Create a list of verified links
        verified_links_content = ListContent[VerifiedLink](items=[approved_link, rejected_link])

        verified_links_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="VerifiedLink",
                domain_code="test_pipe_condition_continue_output_type",
                description="test_pipe_condition_continue_output_type.VerifiedLink",
                structure_class_name="VerifiedLink",
            ),
            content=verified_links_content,
            name="verified_links",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(verified_links_stuff)

        # Run the batch pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="process_verified_links"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        pretty_print(pipe_output, title="PipeBatch output with mixed verdicts")

        # Verify the pipe executed
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Get the output as a list of Constraints
        constraint_list = pipe_output.main_stuff_as_list(item_type=Constraint)

        pretty_print(constraint_list, title="Constraint list")

        if pipe_run_mode.is_live:
            # Compaction: only the approved link yields a Constraint; the rejected link's branch
            # resolved absent and was dropped from the aggregated list.
            assert len(constraint_list.items) == 1, f"Expected 1 constraint, got {len(constraint_list.items)}"
        else:
            # The dry sweep runs every mapped outcome for every item, so both items yield a mock
            # constraint — the continue arm is not selected by expression evaluation in dry mode.
            assert len(constraint_list.items) == 2, f"Expected 2 mock constraints, got {len(constraint_list.items)}"
