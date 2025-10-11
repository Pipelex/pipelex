import tempfile
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StructuredContent, TextContent
from pipelex.tools.func_registry import func_registry
from pipelex.tools.func_registry_utils import FuncRegistryUtils


class FilePath(StructuredContent):
    path: str = Field(description="Path to the file")


class CodebaseFileContent(StructuredContent):
    file_path: str = Field(description="Path to the codebase file")
    file_content: str = Field(description="Content of the codebase file")


class TestCases:
    VALID_ASYNC_FUNCTION = """
async def read_file_content(working_memory: WorkingMemory) -> ListContent[CodebaseFileContent]:
    '''Read the content of related codebase files.'''

    file_paths_list = working_memory.get_stuff_as_list("related_file_paths", item_type=FilePath)

    codebase_files: List[CodebaseFileContent] = []
    for file_path in file_paths_list.items:
        try:
            with open(file_path.path, "r", encoding="utf-8") as file:
                content = file.read()
                codebase_files.append(CodebaseFileContent(file_path=file_path.path, file_content=content))
        except Exception as e:
            codebase_files.append(
                CodebaseFileContent(file_path=file_path.path, file_content=f"# File not found or unreadable: {file_path.path}\\n# Error: {str(e)}")
            )

    return ListContent[CodebaseFileContent](items=codebase_files)
"""

    VALID_SYNC_FUNCTION = """
# Sync function - should be accepted
def sync_function(working_memory: WorkingMemory) -> StructuredContent:
    '''This should be registered - sync functions are now eligible.'''
    pass
"""

    INVALID_FUNCTIONS = """
# Wrong parameter name - should be rejected
def invalid_function_wrong_param_name(other_param: WorkingMemory) -> StructuredContent:
    '''This should not be registered - wrong parameter name.'''
    pass

# Wrong parameter type - should be rejected
def invalid_function_wrong_param_type(working_memory: str) -> StructuredContent:
    '''This should not be registered - wrong parameter type.'''
    pass

# Wrong return type - should be rejected
def invalid_function_wrong_return_type(working_memory: WorkingMemory) -> str:
    '''This should not be registered - wrong return type.'''
    return "test"

# Too many parameters - should be rejected
def invalid_function_too_many_params(working_memory: WorkingMemory, extra_param: str) -> StructuredContent:
    '''This should not be registered - too many parameters.'''
    pass

# No parameters - should be rejected
def invalid_function_no_params() -> StructuredContent:
    '''This should not be registered - no parameters.'''
    pass

# Missing type hints - should be rejected
def invalid_function_no_type_hints(working_memory):
    '''This should not be registered - missing type hints.'''
    pass
"""

    TEST_CASES: ClassVar[list[tuple[str, str, list[str], list[str]]]] = [
        ("valid_async_function", VALID_ASYNC_FUNCTION, ["read_file_content"], []),
        ("valid_sync_function", VALID_SYNC_FUNCTION, ["sync_function"], []),
        (
            "invalid_functions",
            INVALID_FUNCTIONS,
            [],
            [
                "invalid_function_wrong_param_name",
                "invalid_function_wrong_param_type",
                "invalid_function_wrong_return_type",
                "invalid_function_too_many_params",
                "invalid_function_no_params",
                "invalid_function_no_type_hints",
            ],
        ),
    ]


class TestFuncRegistryUtils:
    @pytest.mark.parametrize(
        ("test_name", "function_code", "expected_registered", "expected_not_registered"),
        TestCases.TEST_CASES,
    )
    def test_function_registration_eligibility(
        self,
        test_name: str,  # noqa: ARG002
        function_code: str,
        expected_registered: list[str],
        expected_not_registered: list[str],
    ):
        # Create a temporary directory and file with test functions
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_functions.py"

            # Write the complete test file with imports and function code
            full_code = f"""
from typing import List

from pydantic import Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent


class FilePath(StructuredContent):
    path: str = Field(description="Path to the file")


class CodebaseFileContent(StructuredContent):
    file_path: str = Field(description="Path to the codebase file")
    file_content: str = Field(description="Content of the codebase file")

{function_code}
"""

            test_file.write_text(full_code)

            # Clear the registry to start fresh
            func_registry.teardown()

            # Test the registration
            FuncRegistryUtils.register_funcs_in_folder(folder_path=temp_dir, is_recursive=False)

            # Check that expected functions were registered
            for func_name in expected_registered:
                assert func_registry.has_function(func_name), f"{func_name} should be registered"

                # Verify we can get the function
                registered_func = func_registry.get_function(func_name)
                assert registered_func is not None, f"Registered function {func_name} should be retrievable"
                assert registered_func.__name__ == func_name, f"Function name should match {func_name}"

            # Check that expected functions were NOT registered
            for func_name in expected_not_registered:
                assert not func_registry.has_function(func_name), f"{func_name} should NOT be registered"

    def test_recursive_folder_search(self):
        """Test that recursive folder search works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory structure
            nested_dir = Path(temp_dir) / "subdir"
            nested_dir.mkdir()

            # Create valid async function in root
            root_file = Path(temp_dir) / "root_functions.py"
            root_file.write_text("""
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import TextContent

async def root_function(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="root")
""")

            # Create valid async function in subdirectory
            nested_file = nested_dir / "nested_functions.py"
            nested_file.write_text("""
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import TextContent

async def nested_function(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="nested")
""")

            # Clear the registry
            func_registry.teardown()

            # Test recursive search
            FuncRegistryUtils.register_funcs_in_folder(folder_path=temp_dir, is_recursive=True)

            # Both functions should be registered
            assert func_registry.has_function("root_function"), "root_function should be registered"
            assert func_registry.has_function("nested_function"), "nested_function should be registered"

            # Clear and test non-recursive search
            func_registry.teardown()
            FuncRegistryUtils.register_funcs_in_folder(folder_path=temp_dir, is_recursive=False)

            # Only root function should be registered
            assert func_registry.has_function("root_function"), "root_function should be registered"
            assert not func_registry.has_function("nested_function"), "nested_function should NOT be registered"

    def test_eligibility_check_directly(self):
        # Valid async function
        async def valid_async_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="test")

        # Valid sync function
        def valid_sync_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="test")

        # Test eligibility
        assert func_registry.is_eligible_function(valid_async_function), "Valid async function should be eligible"
        assert func_registry.is_eligible_function(valid_sync_function), "Valid sync function should be eligible"

    def test_register_function_checks_eligibility(self):
        func_registry.teardown()

        # Valid async function
        async def valid_async_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="valid")

        # Valid sync function
        def valid_sync_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="valid")

        # Try to register both functions
        func_registry.register_function(valid_async_function)
        func_registry.register_function(valid_sync_function)

        # Both functions should be registered
        assert func_registry.has_function("valid_async_function"), "Valid async function should be registered"
        assert func_registry.has_function("valid_sync_function"), "Valid sync function should be registered"

        # Test register_functions method as well
        func_registry.teardown()

        async def another_valid_async_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="another_valid_async")

        def another_valid_sync_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="another_valid_sync")

        # Invalid function (wrong parameter name)
        def invalid_function(other_param: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
            return TextContent(text="invalid")

        # Register multiple functions at once - invalid functions should be silently skipped
        func_registry.register_functions([invalid_function, another_valid_async_function, another_valid_sync_function])

        # Valid functions should be registered, invalid function silently skipped
        assert func_registry.has_function("another_valid_async_function"), "Valid async function should be registered"
        assert func_registry.has_function("another_valid_sync_function"), "Valid sync function should be registered"
        assert not func_registry.has_function("invalid_function"), "Invalid function should NOT be registered"


if __name__ == "__main__":
    pytest.main([__file__])
