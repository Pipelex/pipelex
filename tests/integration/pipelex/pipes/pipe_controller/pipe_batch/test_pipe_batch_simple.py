"""Simple integration test for PipeBatch controller."""

from typing import List, cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params import BatchParams, PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import ListContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_controllers.pipe_batch import PipeBatch
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchSimple:
    """Simple integration test for PipeBatch controller."""

    async def test_simple_batch_processing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeBatch with a simple batch processing scenario."""
        # Create PipeBatch instance - it will call the uppercase_transformer pipe from the TOML
        pipe_batch = PipeBatch(
            domain="test_integration",
            code="simple_batch",
            branch_pipe_code="uppercase_transformer",  # This exists in the TOML file
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"text_list": "Text", "text_item": "Text"}),
            output_concept_code="test_integration.UppercaseText",
            batch_params=BatchParams(input_list_stuff_name="text_list", input_item_stuff_name="text_item"),
        )

        # Create test data - list of text items
        text_items = [
            TextContent(text="hello"),
            TextContent(text="world"),
            TextContent(text="test"),
        ]

        text_list_stuff = StuffFactory.make_stuff(
            concept_str="Text",
            content=ListContent[StuffContent](items=cast(List[StuffContent], text_items)),
            name="text_list",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(text_list_stuff)

        # Verify the PipeBatch instance was created correctly
        assert pipe_batch is not None
        assert pipe_batch.domain == "test_integration"
        assert pipe_batch.code == "simple_batch"
        assert pipe_batch.branch_pipe_code == "uppercase_transformer"
        assert pipe_batch.batch_params is not None
        assert pipe_batch.batch_params.input_list_stuff_name == "text_list"
        assert pipe_batch.batch_params.input_item_stuff_name == "text_item"

        # Verify the working memory has the correct structure
        assert working_memory is not None
        text_list = working_memory.get_stuff("text_list")
        assert text_list is not None
        assert isinstance(text_list.content, ListContent)

        # Cast the content to the proper type for type checking
        list_content = cast(ListContent[TextContent], text_list.content)  # type: ignore
        assert len(list_content.items) == 3

        # Verify each item in the list
        for i, item in enumerate(list_content.items):
            assert isinstance(item, TextContent)
            assert item.text == ["hello", "world", "test"][i]

        # Log the initial setup for debugging
        pretty_print(pipe_batch, title="PipeBatch instance")
        pretty_print(working_memory, title="Initial working memory with text list")

        # Actually run the PipeBatch pipe
        pipe_output = await pipe_batch._run_controller_pipe(  # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(job_name=cast(str, request.node.originalname)),  # type: ignore
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
            else:
                assert "DRY RUN" in item.text

        # Verify working memory contains all the expected elements
        final_working_memory = pipe_output.working_memory

        # Original input should still be there
        original_list = final_working_memory.get_stuff("text_list")
        assert original_list is not None
        assert isinstance(original_list.content, ListContent)
        original_items = cast(ListContent[TextContent], original_list.content)  # type: ignore
        assert len(original_items.items) == 3
        assert original_items.items[0].text == "hello"
        assert original_items.items[1].text == "world"
        assert original_items.items[2].text == "test"

        # New result should be added
        batch_result = final_working_memory.get_stuff("batch_result")
        assert batch_result is not None
        assert batch_result.concept_code == "test_integration.UppercaseText"

        # Verify the batch result content matches exactly
        assert isinstance(batch_result.content, ListContent)
        result_list = cast(ListContent[TextContent], batch_result.content)  # type: ignore
        assert len(result_list.items) == 3
        if pipe_run_mode != PipeRunMode.DRY:
            assert result_list.items[0].text == "UPPER: HELLO"
            assert result_list.items[1].text == "UPPER: WORLD"
            assert result_list.items[2].text == "UPPER: TEST"
        else:
            assert "DRY RUN" in result_list.items[0].text
            assert "DRY RUN" in result_list.items[1].text
            assert "DRY RUN" in result_list.items[2].text

        # Verify working memory structure
        assert len(final_working_memory.root) == 2
        assert "text_list" in final_working_memory.root
        assert "batch_result" in final_working_memory.root
        assert final_working_memory.aliases["main_stuff"] == "batch_result"
