from pathlib import Path
from typing import Callable, cast

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_structure.test_structures_basic import RestaurantReview


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeStructureInBatch:
    """PipeBatch iterating PipeStructure over a list of free-form review texts."""

    async def test_batch_with_pipe_structure(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        # RestaurantReview is declared in text_then_structure_helpers.mthds under this domain.
        domain_code = "test_pipe_structure_seq"

        structure_blueprint = PipeStructureBlueprint(
            description="Structure a free-form restaurant review text into a RestaurantReview",
            inputs={"review_text": NativeConceptCode.TEXT},
            output="RestaurantReview",
        )
        structure_pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="structure_one_restaurant_review",
            blueprint=structure_blueprint,
            concept_codes_from_the_same_domain=["RestaurantReview"],
        )
        get_pipe_library().add_new_pipe(structure_pipe)

        batch_blueprint = PipeBatchBlueprint(
            description="Run PipeStructure over a list of free-form review texts",
            branch_pipe_code="structure_one_restaurant_review",
            inputs={"review_texts": NativeConceptCode.TEXT},
            output="RestaurantReview",
            input_list_name="review_texts",
            input_item_name="review_text",
        )
        batch_pipe = PipeFactory[PipeBatch].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="batch_structure_restaurant_reviews",
            blueprint=batch_blueprint,
            concept_codes_from_the_same_domain=["RestaurantReview"],
        )
        get_pipe_library().add_new_pipe(batch_pipe)

        review_texts = [
            TextContent(
                text=(
                    "La Petite Marmite is a tiny family-run bistro in Paris's 11th. The duck confit "
                    "and the leeks vinaigrette are excellent; service is slow on busy nights. About "
                    "$$ for two. Solid 8 out of 10 — a neighbourhood gem."
                ),
            ),
            TextContent(
                text=(
                    "Hopdoddy on King Street is the best burger I've had in Charleston. The wagyu "
                    "with caramelised onions stands out, fries are crisp, and a milkshake rounds it "
                    "off. Loud at peak hours. Maybe a 7. Counts as $$."
                ),
            ),
            TextContent(
                text=(
                    "Don't miss Trattoria Sole in Bologna for the tagliatelle al ragù — pure comfort "
                    "in a bowl. Tortellini in brodo also wonderful. Tiny dining room means you'll "
                    "wait. Easy 9. Pricing leans $$$."
                ),
            ),
        ]
        list_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=ListContent[StuffContent](items=cast("list[StuffContent]", review_texts)),
            name="review_texts",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(list_stuff)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=batch_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name="batch_result",
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_output, title="batch with PipeStructure output")
        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("batch_result") is not None
        result_list = pipe_output.main_stuff_as_list(item_type=StuffContent)
        assert len(result_list.items) == 3
        if pipe_run_mode.is_live:
            for item in result_list.items:
                assert isinstance(item, RestaurantReview)
                assert item.name
                assert item.cuisine
                assert item.city
                assert isinstance(item.overall_rating, int)
                assert item.price_range
                assert isinstance(item.standout_dishes, list)
                assert isinstance(item.caveats, list)
                assert item.one_line_take
