"""Simple integration test for PipeSequence controller."""

from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_controllers.pipe_sequence import PipeSequence, SubPipe
from pipelex.pipe_operators.pipe_llm import PipeLLM
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeSequenceSimple:
    """Simple integration test for PipeSequence controller."""

    async def test_simple_sequence_processing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeSequence with a simple 2-step text transformation scenario."""
        # Create PipeLLM instance for capitalizing text
        capitalize_pipe = PipeLLM(
            domain="test_integration",
            code="capitalize_text",
            inputs=PipeInputSpec.make_from_dict({"input_text": "Text"}),
            output_concept_code="Text",
            pipe_llm_prompt=PipeLLMPrompt(
                code="capitalize_text_prompt",
                domain="test_integration",
                user_text="Transform the following text to uppercase:\n\n@input_text.text\n\nReturn only the uppercase text, nothing else.",
            ),
        )

        # Create PipeLLM instance for adding prefix
        add_prefix_pipe = PipeLLM(
            domain="test_integration",
            code="add_prefix",
            inputs=PipeInputSpec.make_from_dict({"capitalized_text": "Text"}),
            output_concept_code="Text",
            pipe_llm_prompt=PipeLLMPrompt(
                code="add_prefix_prompt",
                domain="test_integration",
                user_text="""Add the prefix "PROCESSED: " to the beginning of the following text:\n\n
                @capitalized_text.text\n\nReturn only the prefixed text, nothing else.""",
            ),
        )

        # Create PipeSequence instance using the PipeLLM instances
        pipe_sequence = PipeSequence(
            domain="test_integration",
            code="simple_sequence",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"input_text": "Text"}),
            output_concept_code="Text",
            sequential_sub_pipes=[
                SubPipe(pipe=capitalize_pipe, output_name="capitalized_text"),
                SubPipe(pipe=add_prefix_pipe, output_name="final_text"),
            ],
        )

        # Create test data - single text input
        input_text_stuff = StuffFactory.make_stuff(
            concept_str="Text",
            content=TextContent(text="hello world"),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the PipeSequence instance was created correctly
        assert pipe_sequence is not None
        assert pipe_sequence.domain == "test_integration"
        assert pipe_sequence.code == "simple_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.sequential_sub_pipes[0].pipe.code == "capitalize_text"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "capitalized_text"
        assert pipe_sequence.sequential_sub_pipes[1].pipe.code == "add_prefix"
        assert pipe_sequence.sequential_sub_pipes[1].output_name == "final_text"

        # Verify the working memory has the correct structure
        assert working_memory is not None
        input_text = working_memory.get_stuff("input_text")
        assert input_text is not None
        assert isinstance(input_text.content, TextContent)
        assert input_text.content.text == "hello world"

        # Log the initial setup for debugging
        pretty_print(pipe_sequence, title="PipeSequence instance")
        pretty_print(working_memory, title="Initial working memory with input text")

        # Actually run the PipeSequence pipe
        pipe_output = await pipe_sequence.run_pipe(
            job_metadata=JobMetadata(job_name=cast(str, request.node.originalname)),  # type: ignore
            working_memory=working_memory,
            output_name="sequence_result",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Log the output for debugging
        pretty_print(pipe_output, title="PipeSequence output")

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the final output
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        # Should be: "hello world" -> "HELLO WORLD" -> "PROCESSED: HELLO WORLD"
        if pipe_run_mode != PipeRunMode.DRY:
            assert final_result.content.text == "PROCESSED: HELLO WORLD"
        else:
            assert "DRY RUN" in final_result.content.text

        # Verify working memory contains all intermediate results
        final_working_memory = pipe_output.working_memory

        # Original input should still be there
        original_input = final_working_memory.get_stuff("input_text")
        assert original_input is not None
        assert isinstance(original_input.content, TextContent)
        assert original_input.content.text == "hello world"

        # Intermediate result (capitalized_text) should be there
        capitalized_result = final_working_memory.get_stuff("capitalized_text")
        assert capitalized_result is not None
        assert isinstance(capitalized_result.content, TextContent)
        if pipe_run_mode != PipeRunMode.DRY:
            assert capitalized_result.content.text == "HELLO WORLD"
        else:
            assert "DRY RUN" in capitalized_result.content.text

        # Final result should be there (stored as final_text, which is the last SubPipe's output_name)
        final_result_in_memory = final_working_memory.get_stuff("final_text")
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        if pipe_run_mode != PipeRunMode.DRY:
            assert final_result_in_memory.content.text == "PROCESSED: HELLO WORLD"
        else:
            assert "DRY RUN" in final_result_in_memory.content.text

        # Verify working memory structure
        assert len(final_working_memory.root) == 3  # input, intermediate, final
        assert "input_text" in final_working_memory.root
        assert "capitalized_text" in final_working_memory.root
        assert "final_text" in final_working_memory.root
        assert final_working_memory.aliases["main_stuff"] == "final_text"
