from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.controller.pipe_condition.pipe_condition import CategoryInput


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionSimple:
    async def test_condition_long_text_processing(
        self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeCondition with long text that should trigger capitalize_long_text pipe."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Text length condition for testing",
            inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
            expression_template="{% if input_text.text|length > 5 %}long{% else %}short{% endif %}",
            outcomes={"long": "capitalize_long_text", "short": "add_prefix_short_text"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code="test_integration",
            pipe_code="text_length_condition",
            blueprint=pipe_condition_blueprint,
        )
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="hello world"),  # 11 characters
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        assert pipe_condition.domain_code == "test_integration"
        assert pipe_condition.code == "text_length_condition"
        assert pipe_condition.outcome_map == {"long": "capitalize_long_text", "short": "add_prefix_short_text"}

        input_text = working_memory.get_stuff("input_text")
        assert input_text is not None
        assert isinstance(input_text.content, TextContent)
        assert input_text.content.text == "hello world"

        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the final output (should be from capitalize_long_text pipe)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        # Should be: "hello world" (11 chars > 5) -> expression="long" -> capitalize_long_text -> "LONG: HELLO WORLD"
        if pipe_run_mode.is_live:
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
        final_result_in_memory = final_working_memory.get_main_stuff()
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        if pipe_run_mode.is_live:
            assert final_result_in_memory.content.text == "LONG: HELLO WORLD"
        assert (
            f"{final_result_in_memory.concept.domain_code}.{final_result_in_memory.concept.code}"
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        )

    async def test_condition_short_text_processing(
        self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeCondition with short text that should trigger add_prefix_short_text pipe."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        # Create PipeCondition instance - pipes are loaded from MTHDS files
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Text length condition for short text testing",
            inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
            expression_template="{% if input_text.text|length > 5 %}long{% else %}short{% endif %}",
            outcomes={"long": "capitalize_long_text", "short": "add_prefix_short_text"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code="test_integration",
            pipe_code="text_length_condition",
            blueprint=pipe_condition_blueprint,
        )

        # Create test data - short text input (<= 5 characters)
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
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
        pipe_output = await pipe_condition.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the final output (should be from add_prefix_short_text pipe)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        # Should be: "hi" (2 chars <= 5) -> expression="short" -> add_prefix_short_text -> "SHORT: hi"
        if pipe_run_mode.is_live:
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
        final_result_in_memory = final_working_memory.get_main_stuff()
        assert final_result_in_memory is not None
        assert isinstance(final_result_in_memory.content, TextContent)
        if pipe_run_mode.is_live:
            assert final_result_in_memory.content.text == "SHORT: hi"
        assert (
            f"{final_result_in_memory.concept.domain_code}.{final_result_in_memory.concept.code}"
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        )

    async def test_condition_dry_run_success(
        self, pipe_run_mode: PipeRunMode, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeCondition dry run with valid inputs using real pipe - should succeed."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        # Create test data using CategoryInput for the real pipe basic_condition_by_category_2
        category_input = CategoryInput(category="small")
        input_data_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="CategoryInput",
                domain_code="test_pipe_condition_2",
                description="test_pipe_condition_2.CategoryInput",
                structure_class_name="CategoryInput",
            ),
            content=category_input,
            name="input_data",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_data_stuff)

        # Run dry run using the real pipe - this should succeed
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="basic_condition_by_category_2"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )
        pretty_print(pipe_output)
        # Verify the dry run succeeded
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # For dry run, the output should be a synthetic result from the chosen pipe (process_small_2)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)

        # Verify working memory structure is preserved
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) >= 1  # At least the result should be there

        # Original input should still be there
        original_input = final_working_memory.get_optional_stuff("input_data")
        if original_input:
            assert isinstance(original_input.content, CategoryInput)
            assert original_input.content.category == "small"

    async def test_condition_dry_run_missing_inputs_failure(
        self, pipe_run_mode: PipeRunMode, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeCondition dry run with missing inputs using real pipe - should fail with PipeRouterError."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        # Create empty working memory - missing required input
        empty_working_memory = WorkingMemoryFactory.make_empty()

        # Run dry run using the real pipe - this should fail with PipeRouterError
        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=get_required_pipe(pipe_code="basic_condition_by_category_2"),
                    pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                    working_memory=empty_working_memory,
                    job_metadata=job_metadata,
                ),
            )

        # Verify the error details
        error = exc_info.value
        assert error.pipe_code == "basic_condition_by_category_2"
        assert "missing required inputs" in str(error)

        # Check the underlying cause is PipeRunInputsError with missing_inputs details
        cause = error.__cause__
        assert isinstance(cause, PipeRunInputsError)
        assert cause.missing_inputs is not None
        assert "input_data" in cause.missing_inputs

    async def test_condition_dry_run_medium_category_validation(
        self, pipe_run_mode: PipeRunMode, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeCondition dry run with medium category - should validate the 'medium' branch."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        # Create test data using CategoryInput for the medium category
        category_input = CategoryInput(category="medium")
        input_data_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="CategoryInput",
                domain_code="test_pipe_condition_2",
                description="test_pipe_condition_2.CategoryInput",
                structure_class_name="CategoryInput",
            ),
            content=category_input,
            name="input_data",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_data_stuff)

        # Run dry run using the real pipe - this should succeed and validate the 'medium' branch
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="basic_condition_by_category_2"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        pretty_print(pipe_output)

        # Verify the dry run succeeded
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify that the dry run correctly validated the pipeline structure for medium category
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)

        # Verify working memory structure
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) >= 1

        # Original input should be preserved in working memory
        original_input = final_working_memory.get_optional_stuff("input_data")
        if original_input:
            assert isinstance(original_input.content, CategoryInput)
            assert original_input.content.category == "medium"
