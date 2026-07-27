from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_structure.test_structures_basic import RestaurantReview


def _count_llm_report_calls(report_spy: MockType) -> int:
    """Count the LLM inference jobs reported during a run.

    Each successful PipeLLM/PipeStructure completion reports exactly one LLMJob to the reporting
    delegate (the canonical per-call hook), so spying on report_inference_job gives a direct count
    of LLM calls — the observation point now that the per-run usage registry has been removed.
    """
    return sum(1 for call in report_spy.call_args_list if isinstance(call.kwargs.get("inference_job"), LLMJob))


def _assert_restaurant_review_shape(review: RestaurantReview) -> None:
    assert review.name
    assert review.cuisine
    assert review.city
    assert isinstance(review.overall_rating, int)
    assert review.price_range
    assert isinstance(review.standout_dishes, list)
    assert isinstance(review.caveats, list)
    assert review.one_line_take


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPreliminaryTextE2E:
    """End-to-end test for the `structuring_method = preliminary_text` elaboration path.

    The MTHDS fixture declares three PipeLLMs with `structuring_method = "preliminary_text"`,
    one per output multiplicity (single / dynamic list / fixed-count list). For each,
    BundleElaborator rewrites the user-facing pipe into a wrapping PipeSequence + a draft
    PipeLLM + a PipeStructure. We verify the structural shape, run the user-facing pipe,
    and assert exactly two LLM calls are issued (one for the draft text, one for the
    structuring step).
    """

    @pytest.mark.parametrize(
        ("pipe_code", "brief", "expected_is_list", "expected_fixed_count"),
        [
            (
                "review_one_restaurant",
                "A small Neapolitan pizza joint that opened recently in Brooklyn, known for its wood-fired ovens.",
                False,
                None,
            ),
            (
                "review_neighborhood_restaurants",
                "Three places worth knowing in Lisbon's Bairro Alto: a tiny tasca, a seafood spot, and a wine bar.",
                True,
                None,
            ),
            (
                "review_two_restaurants",
                "Compare a long-running ramen shop in Tokyo with a newer one chasing the same crowd a few blocks away.",
                True,
                2,
            ),
        ],
    )
    async def test_preliminary_text_runs_through_elaborated_pipes(
        self,
        mocker: MockerFixture,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        pipe_code: str,
        brief: str,
        expected_is_list: bool,
        expected_fixed_count: int | None,
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])

        user_facing_pipe = get_required_pipe(pipe_code=pipe_code)
        assert isinstance(user_facing_pipe, PipeSequence)
        assert len(user_facing_pipe.sequential_sub_pipes) == 2
        assert user_facing_pipe.sequential_sub_pipes[0].pipe_code == f"{pipe_code}__draft_text"
        assert user_facing_pipe.sequential_sub_pipes[1].pipe_code == f"{pipe_code}__structure"

        structure_step = get_required_pipe(pipe_code=f"{pipe_code}__structure")
        assert isinstance(structure_step, PipeStructure)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text=brief),
                name="restaurant_brief",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=user_facing_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        report_spy = mocker.spy(get_report_delegate(), "report_inference_job")
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)
        pretty_print(pipe_output, title=f"preliminary_text e2e output ({pipe_code})")

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("draft_text") is not None
        if pipe_run_mode.is_live:
            # Exactly two LLM calls: one for the draft text, one for the structuring step.
            assert _count_llm_report_calls(report_spy) == 2
            assert pipe_output.main_stuff.concept.code == "RestaurantReview"
            if expected_is_list:
                items = pipe_output.main_stuff_as_items(item_type=RestaurantReview)
                if expected_fixed_count is not None:
                    assert len(items) == expected_fixed_count
                for item in items:
                    _assert_restaurant_review_shape(item)
            else:
                _assert_restaurant_review_shape(pipe_output.main_stuff_as(content_type=RestaurantReview))
