"""Simple integration test for PipeCondition controller."""

from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_controllers.pipe_condition import PipeCondition
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionSimple:
    """Simple integration test for PipeCondition controller."""

    async def test_condition_long_text_processing(self, request: FixtureRequest):
        """Test PipeCondition with long text that should trigger capitalize_long_text pipe."""
        # Create PipeCondition instance - pipes are loaded from TOML files
        pipe_condition = PipeCondition(
            domain="test_integration",
            code="text_length_condition",
            inputs=PipeInputSpec(root={"input_text": "Text"}),
            output_concept_code="Text",
            expression_template="{% if input_text.text|length > 5 %}long{% else %}short{% endif %}",
            pipe_map={"long": "capitalize_long_text", "short": "add_prefix_short_text"},
        )

        # Create test data - long text input (> 5 characters)
        input_text_stuff = StuffFactory.make_stuff(
            concept_str="Text",
            content=TextContent(text="hello world"),  # 11 characters
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the PipeCondition instance was created correctly
        assert pipe_condition.domain == "test_integration"
        assert pipe_condition.code == "text_length_condition"
        assert pipe_condition.pipe_map["long"] == "capitalize_long_text"
        assert pipe_condition.pipe_map["short"] == "add_prefix_short_text"

        # Verify the working memory has the correct structure
        input_text = working_memory.get_stuff("input_text")
        assert input_text is not None
        assert isinstance(input_text.content, TextContent)
        assert input_text.content.text == "hello world"

        # Actually run the PipeCondition pipe
        pipe_output = await pipe_condition._run_controller_pipe(  # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(job_name=cast(str, request.node.originalname)),  # type: ignore
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            output_name="condition_result",
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the final output (should be from capitalize_long_text pipe)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        # Should be: "hello world" (11 chars > 5) -> expression="long" -> capitalize_long_text -> "LONG: HELLO WORLD"
        assert final_result.content.text == "LONG: HELLO WORLD"

        # Verify working memory structure
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 2  # original input + condition result

        # Original input should still be there
        original_input = final_working_memory.get_stuff("input_text")
        assert original_input is not None
        assert isinstance(original_input.content, TextContent)
        assert original_input.content.text == "hello world"

        # Final result should be there with correct name and content
        final_result_in_memory = final_working_memory.get_stuff("condition_result")
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        assert final_result_in_memory.content.text == "LONG: HELLO WORLD"
        assert final_result_in_memory.concept_code == "native.Text"

    async def test_condition_short_text_processing(self, request: FixtureRequest):
        """Test PipeCondition with short text that should trigger add_prefix_short_text pipe."""
        # Create PipeCondition instance - pipes are loaded from TOML files
        pipe_condition = PipeCondition(
            domain="test_integration",
            code="text_length_condition",
            inputs=PipeInputSpec(root={"input_text": "Text"}),
            output_concept_code="Text",
            expression_template="{% if input_text.text|length > 5 %}long{% else %}short{% endif %}",
            pipe_map={"long": "capitalize_long_text", "short": "add_prefix_short_text"},
        )

        # Create test data - short text input (<= 5 characters)
        input_text_stuff = StuffFactory.make_stuff(
            concept_str="Text",
            content=TextContent(text="hi"),  # 2 characters
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the working memory has the correct structure
        input_text = working_memory.get_stuff("input_text")
        assert input_text is not None
        assert isinstance(input_text.content, TextContent)
        assert input_text.content.text == "hi"

        # Actually run the PipeCondition pipe
        pipe_output = await pipe_condition._run_controller_pipe(  # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(job_name=cast(str, request.node.originalname)),  # type: ignore
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            output_name="condition_result",
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the final output (should be from add_prefix_short_text pipe)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        # Should be: "hi" (2 chars <= 5) -> expression="short" -> add_prefix_short_text -> "SHORT: hi"
        assert final_result.content.text == "SHORT: hi"

        # Verify working memory structure
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 2  # original input + condition result

        # Original input should still be there
        original_input = final_working_memory.get_stuff("input_text")
        assert original_input is not None
        assert isinstance(original_input.content, TextContent)
        assert original_input.content.text == "hi"

        # Final result should be there with correct name and content
        final_result_in_memory = final_working_memory.get_stuff("condition_result")
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        assert final_result_in_memory.content.text == "SHORT: hi"
        assert final_result_in_memory.concept_code == "native.Text"
