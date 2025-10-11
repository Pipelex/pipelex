from __future__ import annotations

from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import ListContent, StuffContent, TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_factory import PipeBatchFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchSimple:
    """Simple integration test for PipeBatch controller."""

    async def test_simple_batch_processing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeBatch with a simple batch processing scenario."""
        # Create PipeBatch instance - it will call the uppercase_transformer pipe from the PLX
        domain = "test_integration"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept1",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept1"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept2",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept2"],
        )
        concept_library = get_concept_provider()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_batch_blueprint = PipeBatchBlueprint(
            description="Simple batch processing test",
            branch_pipe_code="uppercase_transformer",  # This exists in the PLX file
            inputs={
                "text_list": InputRequirementBlueprint(concept=concept_1.concept_string),
                "text_item": InputRequirementBlueprint(concept=concept_2.concept_string),
            },
            output=concept_2.concept_string,
            input_list_name="text_list",
            input_item_name="text_item",
        )

        pipe_batch = PipeBatchFactory.make_from_blueprint(
            domain=domain,
            pipe_code="simple_batch",
            blueprint=pipe_batch_blueprint,
            concept_codes_from_the_same_domain=["TestConcept1", "TestConcept2"],
        )

        # Create test data - list of text items
        text_items = [
            TextContent(text="hello"),
            TextContent(text="world"),
            TextContent(text="test"),
        ]

        text_list_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            content=ListContent[StuffContent](items=cast("list[StuffContent]", text_items)),
            name="text_list",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(text_list_stuff)

        # Verify the PipeBatch instance was created correctly
        assert pipe_batch is not None
        assert pipe_batch.domain == domain
        assert pipe_batch.code == "simple_batch"
        assert pipe_batch.branch_pipe_code == "uppercase_transformer"
        assert pipe_batch.batch_params is not None
        assert pipe_batch.batch_params.input_list_stuff_name == "text_list"
        assert pipe_batch.batch_params.input_item_stuff_name == "text_item"

        # Verify the working memory has the correct structure
        assert working_memory is not None
        text_list = working_memory.get_stuff_as_list("text_list", item_type=TextContent)
        assert text_list is not None
        assert len(text_list.items) == 3

        # Verify each item in the list
        for i, item in enumerate(text_list.items):
            assert isinstance(item, TextContent)
            assert item.text == ["hello", "world", "test"][i]

        # Log the initial setup for debugging
        pretty_print(pipe_batch, title="PipeBatch instance")
        pretty_print(working_memory, title="Initial working memory with text list")

        # Actually run the PipeBatch pipe
        pipe_output = await pipe_batch.run_pipe(  # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            output_name="batch_result",
        )

        # Log the output for debugging
        pretty_print(pipe_output, title="PipeBatch output")

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the output is a ListContent with processed items
        output_list = pipe_output.main_stuff_as_list(item_type=TextContent)
        assert len(output_list.items) == 3

        # Test each individual output item
        expected_results = ["UPPER: HELLO", "UPPER: WORLD", "UPPER: TEST"]
        for i, item in enumerate(output_list.items):
            assert isinstance(item, TextContent)
            if pipe_run_mode != PipeRunMode.DRY:
                assert item.text == expected_results[i], f"Item {i}: expected '{expected_results[i]}', got '{item.text}'"

        # Verify working memory contains all the expected elements
        final_working_memory = pipe_output.working_memory

        # Original input should still be there
        original_list = final_working_memory.get_stuff_as_list("text_list", item_type=TextContent)
        assert original_list is not None
        assert len(original_list.items) == 3
        assert original_list.items[0].text == "hello"
        assert original_list.items[1].text == "world"
        assert original_list.items[2].text == "test"

        # New result should be added
        batch_result = final_working_memory.get_stuff("batch_result")
        assert batch_result is not None
        assert batch_result.concept.code == concept_2.code
        assert batch_result.concept.domain == domain

        # Verify the batch result content matches exactly
        assert isinstance(batch_result.content, ListContent)
        result_list = batch_result.as_list_of_fixed_content_type(item_type=TextContent)
        assert len(result_list.items) == 3
        if pipe_run_mode != PipeRunMode.DRY:
            assert result_list.items[0].text == "UPPER: HELLO"
            assert result_list.items[1].text == "UPPER: WORLD"
            assert result_list.items[2].text == "UPPER: TEST"

        # Verify working memory structure
        assert len(final_working_memory.root) == 2
        assert "text_list" in final_working_memory.root
        assert "batch_result" in final_working_memory.root
        assert final_working_memory.aliases["main_stuff"] == "batch_result"
