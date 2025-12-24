"""Integration test demonstrating the issue with PipeCondition continue outcome.

When PipeCondition routes to 'continue', the main_stuff still contains the input type
(VerifiedLink) instead of the declared output type (Constraint[]).
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.controller.pipe_condition.pipe_condition_continue_output_type import (
    Constraint,
    VerifiedLink,
)


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionContinueOutputType:
    """Test demonstrating the output type issue when PipeCondition uses continue outcome."""

    async def test_continue_outcome_leaves_wrong_main_stuff_type(
        self,
        load_test_library: Callable[[list[Path]], None],
    ):
        """Test that when condition routes to 'continue', the main_stuff has wrong type.

        The PipeCondition declares output = "Constraint[]" but when the outcome is
        'continue' (for rejected links), the main_stuff still contains VerifiedLink
        instead of an empty list of Constraint or the expected output type.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])

        # Create a rejected VerifiedLink - this will trigger the "continue" outcome
        verified_link = VerifiedLink(
            source="EventA",
            target="EventB",
            verdict="rejected",  # This will route to "continue"
        )

        verified_link_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="VerifiedLink",
                domain_code="test_pipe_condition_continue_output_type",
                description="test_pipe_condition_continue_output_type.VerifiedLink",
                structure_class_name="VerifiedLink",
            ),
            content=verified_link,
            name="verified_link",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(verified_link_stuff)

        # Run the pipe - since verdict is "rejected", it will route to "continue"
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="build_or_skip"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
                working_memory=working_memory,
                job_metadata=JobMetadata(),
            ),
        )

        pretty_print(pipe_output, title="PipeCondition output with 'continue' outcome")

        # Verify the pipe executed
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # The declared output type is Constraint[] but since the condition routed to
        # 'continue', the main_stuff is still VerifiedLink - this should fail!
        # This demonstrates the bug: when "continue" is chosen, the output type
        # doesn't match the declared output of the PipeCondition.
        constraint_list = pipe_output.main_stuff_as_list(item_type=Constraint)

        # If we got here, verify the list (which we shouldn't, this should fail above)
        pretty_print(constraint_list, title="Constraint list (unexpected success)")
        assert constraint_list is not None
