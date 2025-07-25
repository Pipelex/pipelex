from typing import List

import pytest
from pydantic import Field
from pytest import FixtureRequest

from pipelex import log, pretty_print
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import StructuredContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.exceptions import DryRunError
from pipelex.hub import get_report_delegate
from pipelex.pipe_operators.pipe_func import PipeFunc
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.func_registry import func_registry


# Test structure classes
class TestResult(StructuredContent):
    """Test result structure for PipeFunc dry run testing"""

    message: str = Field(..., description="Test message")
    value: int = Field(..., description="Test value")


class ComplexResult(StructuredContent):
    """Complex test result structure"""

    name: str = Field(..., description="Name field")
    items: List[str] = Field(default_factory=list, description="List of items")
    nested: TestResult = Field(..., description="Nested test result")


# Test functions to register
def test_function_with_stuff_content() -> TestResult:
    """Test function that returns a StuffContent subclass"""
    return TestResult(message="test", value=42)


def test_function_with_complex_type() -> ComplexResult:
    """Test function that returns a complex StuffContent"""
    return ComplexResult(name="test", items=["a", "b", "c"], nested=TestResult(message="nested", value=99))


def test_function_no_annotation():
    """Test function without return type annotation"""
    return "no annotation"


def test_function_invalid_return() -> int:
    """Test function with invalid return type (not StuffContent)"""
    return 123


def test_function_with_inputs() -> TestResult:
    """Test function that requires inputs"""
    return TestResult(message="with inputs", value=123)


@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeFuncDryRun:
    def setup_method(self):
        """Register test functions before each test"""
        func_registry.register_function(test_function_with_stuff_content)
        func_registry.register_function(test_function_with_complex_type)
        func_registry.register_function(test_function_no_annotation)
        func_registry.register_function(test_function_invalid_return)
        func_registry.register_function(test_function_with_inputs)

    def teardown_method(self):
        """Clean up registered functions after each test"""
        try:
            func_registry.unregister_function(test_function_with_stuff_content)
            func_registry.unregister_function(test_function_with_complex_type)
            func_registry.unregister_function(test_function_no_annotation)
            func_registry.unregister_function(test_function_invalid_return)
            func_registry.unregister_function(test_function_with_inputs)
        except Exception:
            pass  # Ignore errors during cleanup

    async def test_pipe_func_dry_run_with_stuff_content(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with a function returning StuffContent"""

        # Create PipeFunc
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func",
            function_name="test_function_with_stuff_content",
            output_concept_code="test.TestResult",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_empty()

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Run the pipe in dry run mode
        pipe_output = await pipe_func.run_pipe(
            job_metadata=JobMetadata(),
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
        )

        # Log output and generate report
        pretty_print(pipe_output, title="PipeFunc Dry Run Output - StuffContent")
        get_report_delegate().generate_report()

        # Assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the mock content is of the expected type
        mock_content = pipe_output.main_stuff.content
        assert isinstance(mock_content, TestResult)
        assert isinstance(mock_content.message, str)
        assert isinstance(mock_content.value, int)

        log.info("Dry run completed successfully for StuffContent return type")

    async def test_pipe_func_dry_run_with_complex_type(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with a function returning complex StuffContent"""

        # Create PipeFunc
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func_complex",
            function_name="test_function_with_complex_type",
            output_concept_code="test.ComplexResult",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_empty()

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Run the pipe in dry run mode
        pipe_output = await pipe_func.run_pipe(
            job_metadata=JobMetadata(),
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
        )

        # Log output and generate report
        pretty_print(pipe_output, title="PipeFunc Dry Run Output - Complex")

        # Assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the mock content is of the expected type
        mock_content = pipe_output.main_stuff.content
        assert isinstance(mock_content, ComplexResult)
        assert isinstance(mock_content.name, str)
        assert isinstance(mock_content.items, list)
        assert isinstance(mock_content.nested, TestResult)

        log.info("Dry run completed successfully for complex StuffContent return type")

    async def test_pipe_func_dry_run_with_inputs_present(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with inputs that are present in working memory"""

        # Create PipeFunc with inputs
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func_with_inputs",
            function_name="test_function_with_inputs",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"input_text": "native.Text", "input_data": "test.TestResult"}),
            output_concept_code="test.TestResult",
        )

        # Create working memory with required inputs
        input_text_stuff = StuffFactory.make_stuff(concept_str="native.Text", content=TextContent(text="test input"), name="input_text")
        input_data_stuff = StuffFactory.make_stuff(
            concept_str="test.TestResult", content=TestResult(message="input data", value=456), name="input_data"
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([input_text_stuff, input_data_stuff])

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Run the pipe in dry run mode - should succeed
        pipe_output = await pipe_func.run_pipe(
            job_metadata=JobMetadata(),
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
        )

        # Assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the mock content is of the expected type
        mock_content = pipe_output.main_stuff.content
        assert isinstance(mock_content, TestResult)

        log.info("Dry run completed successfully with required inputs present")

    async def test_pipe_func_dry_run_with_missing_inputs(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with missing inputs raises DryRunError"""

        # Create PipeFunc with inputs
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func_missing_inputs",
            function_name="test_function_with_inputs",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"input_text": "native.Text", "missing_input": "test.TestResult"}),
            output_concept_code="test.TestResult",
        )

        # Create working memory with only partial inputs
        input_text_stuff = StuffFactory.make_stuff(concept_str="native.Text", content=TextContent(text="test input"), name="input_text")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Expect DryRunError to be raised due to missing input
        with pytest.raises(DryRunError, match="Required input 'missing_input' not found in working memory"):
            await pipe_func.run_pipe(
                job_metadata=JobMetadata(),
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        log.info("Correctly raised DryRunError for missing inputs")

    async def test_pipe_func_dry_run_no_annotation(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with a function without return type annotation raises DryRunError"""

        # Create PipeFunc
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func_no_annotation",
            function_name="test_function_no_annotation",
            output_concept_code="native.Text",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_empty()

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Expect DryRunError to be raised
        with pytest.raises(DryRunError, match="Function 'test_function_no_annotation' has no return type annotation"):
            await pipe_func.run_pipe(
                job_metadata=JobMetadata(),
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        log.info("Correctly raised DryRunError for function without annotation")

    async def test_pipe_func_dry_run_invalid_return_type(
        self,
        request: FixtureRequest,
    ):
        """Test PipeFunc dry run with a function having invalid return type raises DryRunError"""

        # Create PipeFunc
        pipe_func = PipeFunc(
            domain="test",
            code="test_pipe_func_invalid",
            function_name="test_function_invalid_return",
            output_concept_code="native.Text",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_empty()

        # Create dry run params
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)

        # Expect DryRunError to be raised due to invalid return type
        with pytest.raises(DryRunError, match="Failed to get type hints for function 'test_function_invalid_return'"):
            await pipe_func.run_pipe(
                job_metadata=JobMetadata(),
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        log.info("Correctly raised DryRunError for function with invalid return type")
