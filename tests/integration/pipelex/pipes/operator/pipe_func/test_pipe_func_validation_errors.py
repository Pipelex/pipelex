"""Tests for PipeFunc validation error reporting.

This module tests that when a @pipe_func decorated function has issues
(like missing return type), the validation provides clear error messages
instead of just "function not found".
"""

import tempfile
from pathlib import Path
from typing import ClassVar

import pytest

from pipelex.libraries.exceptions import LibraryError
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.registries.func_registry import func_registry


class TestData:
    """Test data for pipe_func validation error tests."""

    @staticmethod
    def make_plx_content(function_name: str) -> str:
        """Generate PLX content for testing a specific function."""
        return f"""
domain = "test_pipe_func_validation"
description = "Test bundle for pipe_func validation error reporting"

[pipe.test_pipe_func]
type = "PipeFunc"
description = "Test pipe that uses a function"
function_name = "{function_name}"
output = "Text"
"""

    PLX_CONTENT_WITH_PIPE_FUNC: ClassVar[str] = """
domain = "test_pipe_func_validation"
description = "Test bundle for pipe_func validation error reporting"

[pipe.test_pipe_func]
type = "PipeFunc"
description = "Test pipe that uses a function without return type"
function_name = "my_func_no_return_type"
output = "Text"
"""

    FUNC_WITH_DECORATOR_NO_RETURN_TYPE: ClassVar[str] = """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def my_func_no_return_type(working_memory: WorkingMemory):
    '''Function with @pipe_func decorator but NO return type annotation.'''
    return TextContent(text="test")
"""

    FUNC_WITH_DECORATOR_VALID: ClassVar[str] = """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def my_func_no_return_type(working_memory: WorkingMemory) -> TextContent:
    '''Function with @pipe_func decorator WITH return type annotation.'''
    return TextContent(text="test")
"""

    # Test cases for different ineligibility reasons
    # Each tuple: (function_name, python_code, expected_error_substring)
    INELIGIBLE_FUNCTION_CASES: ClassVar[list[tuple[str, str, str]]] = [
        # Case 1: Missing return type annotation
        (
            "func_missing_return_type",
            """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_missing_return_type(working_memory: WorkingMemory):
    return TextContent(text="test")
""",
            "return type annotation",
        ),
        # Case 2: Wrong parameter name
        (
            "func_wrong_param_name",
            """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_wrong_param_name(other_memory: WorkingMemory) -> TextContent:
    return TextContent(text="test")
""",
            "working_memory",
        ),
        # Case 3: Wrong parameter type
        (
            "func_wrong_param_type",
            """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_wrong_param_type(working_memory: str) -> TextContent:
    return TextContent(text="test")
""",
            "WorkingMemory",
        ),
        # Case 4: Wrong return type (not StuffContent subclass)
        (
            "func_wrong_return_type",
            """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_wrong_return_type(working_memory: WorkingMemory) -> str:
    return "test"
""",
            "StuffContent",
        ),
        # Case 5: Too many parameters
        (
            "func_too_many_params",
            """
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_too_many_params(working_memory: WorkingMemory, extra: str) -> TextContent:
    return TextContent(text="test")
""",
            "exactly one parameter",
        ),
        # Case 6: No parameters
        (
            "func_no_params",
            """
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_no_params() -> TextContent:
    return TextContent(text="test")
""",
            "no parameters",
        ),
        # Case 7: Missing parameter type annotation
        (
            "func_missing_param_type",
            """
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func

@pipe_func()
async def func_missing_param_type(working_memory) -> TextContent:
    return TextContent(text="test")
""",
            "type annotation",
        ),
    ]


@pytest.mark.asyncio(loop_scope="class")
class TestPipeFuncValidationErrors:
    """Tests for PipeFunc validation error reporting when @pipe_func decorated functions have issues."""

    def setup_method(self):
        """Clear the func_registry before each test."""
        func_registry.teardown()

    def teardown_method(self):
        """Clean up the func_registry after each test."""
        func_registry.teardown()

    async def test_pipe_func_missing_return_type_reports_clear_error(self):
        """Test that a @pipe_func decorated function without return type gives a clear error.

        When a function has @pipe_func decorator but is missing return type annotation,
        the error should explain the issue clearly instead of saying "function not found".

        BUG: Currently, the error says "Function 'my_func_no_return_type' not found in registry"
        without explaining WHY (the function was found but has no return type annotation).
        The fix should provide a clear error explaining that the function exists but is
        not eligible due to missing return type annotation.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .plx file
            plx_file = temp_path / "test_bundle.plx"
            plx_file.write_text(TestData.PLX_CONTENT_WITH_PIPE_FUNC)

            # Create the .py file with the function (missing return type)
            py_file = temp_path / "my_funcs.py"
            py_file.write_text(TestData.FUNC_WITH_DECORATOR_NO_RETURN_TYPE)

            # Validate the bundle - should fail with a CLEAR error message
            # Currently raises LibraryError, but ValidateBundleError is also acceptable
            with pytest.raises((ValidateBundleError, LibraryError)) as exc_info:
                await validate_bundle(
                    plx_file_path=plx_file,
                    library_dirs=[temp_path],
                )

            error = exc_info.value
            error_message = str(error)

            # The error should mention the function name
            assert "my_func_no_return_type" in error_message, f"Error message should mention the function name. Got: {error_message}"

            # The error should explain WHY the function is not eligible
            # It should mention "return type" or similar - NOT just "not found"
            error_mentions_return_type = (
                "return type" in error_message.lower()
                or "return annotation" in error_message.lower()
                or "missing return" in error_message.lower()
                or "no return" in error_message.lower()
            )
            error_mentions_not_found = "not found" in error_message.lower()

            # BUG ASSERTION: If the error says "not found", it should ALSO explain why
            # Currently this assertion FAILS because the error just says "not found"
            # without explaining the actual issue (missing return type annotation)
            if error_mentions_not_found:
                assert error_mentions_return_type, (
                    f"BUG: Error says 'not found' but doesn't explain why the @pipe_func "
                    f"decorated function is not eligible (missing return type annotation). "
                    f"Got: {error_message}"
                )

    async def test_pipe_func_with_return_type_validates_successfully(self):
        """Test that a properly defined @pipe_func decorated function validates successfully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .plx file
            plx_file = temp_path / "test_bundle.plx"
            plx_file.write_text(TestData.PLX_CONTENT_WITH_PIPE_FUNC)

            # Create the .py file with the function (WITH return type)
            py_file = temp_path / "my_funcs.py"
            py_file.write_text(TestData.FUNC_WITH_DECORATOR_VALID)

            # Validate the bundle - should succeed
            result = await validate_bundle(
                plx_file_path=plx_file,
                library_dirs=[temp_path],
            )

            assert result is not None
            assert len(result.pipes) > 0

    async def test_pipe_func_decorated_but_ineligible_not_silently_ignored(self):
        """Test that @pipe_func decorated but ineligible functions are not silently ignored.

        When scanning a directory for functions, if a function has @pipe_func decorator
        but doesn't meet eligibility criteria, we should record/report this instead of
        silently ignoring it.

        This test specifically verifies that when a function has the @pipe_func decorator
        but is missing a return type annotation, the error message should explain this
        issue rather than just saying "function not found".
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .py file with the function (missing return type)
            py_file = temp_path / "my_funcs.py"
            py_file.write_text(TestData.FUNC_WITH_DECORATOR_NO_RETURN_TYPE)

            # Create .plx file that references the function
            plx_file = temp_path / "test_bundle.plx"
            plx_file.write_text(TestData.PLX_CONTENT_WITH_PIPE_FUNC)

            # Try to validate - should fail with informative error
            with pytest.raises((ValidateBundleError, LibraryError)) as exc_info:
                await validate_bundle(
                    plx_file_path=plx_file,
                    library_dirs=[temp_path],
                )

            error = exc_info.value
            error_message = str(error)

            # The function should be mentioned in the error
            assert "my_func_no_return_type" in error_message

            # BUG: Currently this fails with "function not found" which is misleading
            # After the fix, it should mention the actual issue (missing return type)
            # This test documents the expected behavior after the bug is fixed
            error_explains_issue = (
                "return type" in error_message.lower()
                or "return annotation" in error_message.lower()
                or "missing return" in error_message.lower()
                or "no return" in error_message.lower()
                or "not eligible" in error_message.lower()
            )
            assert error_explains_issue, (
                f"BUG: Error should explain why the @pipe_func decorated function is not eligible, not just say 'not found'. Got: {error_message}"
            )

    @pytest.mark.parametrize(
        ("function_name", "python_code", "expected_error_substring"),
        TestData.INELIGIBLE_FUNCTION_CASES,
        ids=[case[0] for case in TestData.INELIGIBLE_FUNCTION_CASES],
    )
    async def test_ineligible_function_returns_correct_error(
        self,
        function_name: str,
        python_code: str,
        expected_error_substring: str,
    ):
        """Test that each type of ineligible @pipe_func function returns the correct error message.

        This parametrized test verifies that when a function has @pipe_func decorator but
        is not eligible for various reasons, the error message clearly explains the specific
        issue rather than just saying "function not found".
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .plx file referencing the function
            plx_file = temp_path / "test_bundle.plx"
            plx_file.write_text(TestData.make_plx_content(function_name))

            # Create the .py file with the ineligible function
            py_file = temp_path / "my_funcs.py"
            py_file.write_text(python_code)

            # Validate the bundle - should fail with a specific error message
            with pytest.raises((ValidateBundleError, LibraryError)) as exc_info:
                await validate_bundle(
                    plx_file_path=plx_file,
                    library_dirs=[temp_path],
                )

            error = exc_info.value
            error_message = str(error)

            # The error should mention the function name
            assert function_name in error_message, f"Error message should mention the function name '{function_name}'. Got: {error_message}"

            # The error should mention that the function is not eligible (has decorator but failed)
            assert "not eligible" in error_message.lower(), f"Error should mention that the function is 'not eligible'. Got: {error_message}"

            # The error should contain the expected error substring explaining the specific issue
            assert expected_error_substring.lower() in error_message.lower(), (
                f"Error should mention '{expected_error_substring}' to explain the specific issue. Got: {error_message}"
            )
