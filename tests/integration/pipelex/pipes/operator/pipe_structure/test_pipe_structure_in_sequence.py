from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_structure.test_structures_basic import RestaurantReview


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeStructureInSequence:
    """Hand-authored PipeSequence wrapping a PipeLLM + PipeStructure (no elaboration sugar)."""

    async def test_sequence_with_pipe_structure(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        domain_code = "test_pipe_structure_seq"

        # The structuring step is authored explicitly here — no preliminary_text elaboration is involved,
        # so this test covers the path where users compose PipeStructure into a PipeSequence by hand.
        structure_blueprint = PipeStructureBlueprint(
            description="Turn the draft restaurant review text into a RestaurantReview",
            inputs={"draft_text": NativeConceptCode.TEXT},
            output="RestaurantReview",
        )
        structure_pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="structure_restaurant_review",
            blueprint=structure_blueprint,
            concept_codes_from_the_same_domain=["RestaurantReview"],
        )
        get_pipe_library().add_new_pipe(structure_pipe)

        sequence_blueprint = PipeSequenceBlueprint(
            description="Draft a free-form review via PipeLLM, then structure it via PipeStructure",
            inputs={"restaurant_brief": NativeConceptCode.TEXT},
            output="RestaurantReview",
            steps=[
                SubPipeBlueprint(pipe="draft_restaurant_review_text", result="draft_text"),
                SubPipeBlueprint(pipe="structure_restaurant_review", result="restaurant_review"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="text_then_structure_restaurant_review",
            blueprint=sequence_blueprint,
            concept_codes_from_the_same_domain=["RestaurantReview"],
        )
        get_pipe_library().add_new_pipe(sequence_pipe)
        assert len(sequence_pipe.sequential_sub_pipes) == 2

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="A bustling sushi counter in San Francisco's Mission district, popular for its omakase."),
                name="restaurant_brief",
            ),
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=sequence_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_output, title="sequence with PipeStructure output")
        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("draft_text") is not None
        assert pipe_output.working_memory.get_stuff("restaurant_review") is not None
        if pipe_run_mode.is_live:
            review = pipe_output.main_stuff_as(content_type=RestaurantReview)
            assert review.name
            assert review.cuisine
            assert review.city
            assert isinstance(review.overall_rating, int)
            assert review.price_range
            assert isinstance(review.standout_dishes, list)
            assert isinstance(review.caveats, list)
            assert review.one_line_take
