"""Simple integration test for PipeSequence controller."""

from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_concept_library, get_native_concept
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_factory import PipeSequenceFactory
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeSequenceSimple:
    """Simple integration test for PipeSequence controller."""

    async def test_simple_sequence_processing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeSequence with a simple 2-step text transformation scenario."""
        domain = "test_integration"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept1",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept1"],
        )
        concept_library = get_concept_library()
        concept_library.add_concepts([concept_1])
        concept_2 = get_native_concept(native_concept=NativeConceptCode.TEXT)

        # Create PipeSequence instance - pipes are loaded from PLX files
        pipe_sequence_blueprint = PipeSequenceBlueprint(
            description="Simple sequence for text processing",
            inputs={"input_text": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            steps=[
                SubPipeBlueprint(pipe="capitalize_text", result="capitalized_text"),
                SubPipeBlueprint(pipe="add_prefix", result="final_text"),
            ],
        )

        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain="test_integration",
            pipe_code="simple_sequence",
            blueprint=pipe_sequence_blueprint,
        )

        # Create test data - single text input
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept_from_enum(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="hello world"),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the PipeSequence instance was created correctly
        assert pipe_sequence is not None
        assert pipe_sequence.domain == "test_integration"
        assert pipe_sequence.code == "simple_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.sequential_sub_pipes[0].pipe_code == "capitalize_text"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "capitalized_text"
        assert pipe_sequence.sequential_sub_pipes[1].pipe_code == "add_prefix"
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
            job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
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
            assert final_result.content.text in {"PROCESSED: HELLO WORLD", "PROCESSED: hello world"}

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

        # Final result should be there (stored as final_text, which is the last SubPipe's output_name)
        final_result_in_memory = final_working_memory.get_stuff("final_text")
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        if pipe_run_mode != PipeRunMode.DRY:
            assert final_result_in_memory.content.text == "PROCESSED: HELLO WORLD"

        # Verify working memory structure
        assert len(final_working_memory.root) == 3  # input, intermediate, final
        assert "input_text" in final_working_memory.root
        assert "capitalized_text" in final_working_memory.root
        assert "final_text" in final_working_memory.root
        assert final_working_memory.aliases["main_stuff"] == "final_text"
