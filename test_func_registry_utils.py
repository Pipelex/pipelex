#!/usr/bin/env python3
"""Test script for FuncRegistryUtils"""

import tempfile
from pathlib import Path

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.func_registry import func_registry
from pipelex.tools.func_registry_utils import FuncRegistryUtils


class FilePath(StructuredContent):
    """A path to a file in the codebase."""

    path: str = Field(description="Path to the file")


class CodebaseFileContent(StructuredContent):
    """Content of a codebase file."""

    file_path: str = Field(description="Path to the codebase file")
    file_content: str = Field(description="Content of the codebase file")


def test_func_registry_utils():
    """Test the FuncRegistryUtils implementation."""

    # Create a temporary directory and file with the example function
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "test_functions.py"

        # Write the example function to the test file
        test_file.write_text("""
from typing import List

from pydantic import Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent


class FilePath(StructuredContent):
    path: str = Field(description="Path to the file")


class CodebaseFileContent(StructuredContent):
    file_path: str = Field(description="Path to the codebase file")
    file_content: str = Field(description="Content of the codebase file")


def read_file_content(working_memory: WorkingMemory) -> ListContent[CodebaseFileContent]:
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


def invalid_function_wrong_param_name(other_param: WorkingMemory) -> StructuredContent:
    '''This should not be registered - wrong parameter name.'''
    pass


def invalid_function_wrong_param_type(working_memory: str) -> StructuredContent:
    '''This should not be registered - wrong parameter type.'''
    pass


def invalid_function_wrong_return_type(working_memory: WorkingMemory) -> str:
    '''This should not be registered - wrong return type.'''
    return "test"


def invalid_function_too_many_params(working_memory: WorkingMemory, extra_param: str) -> StructuredContent:
    '''This should not be registered - too many parameters.'''
    pass
""")

        # Clear the registry to start fresh
        func_registry.teardown()

        # Test the registration
        FuncRegistryUtils.register_funcs_in_folder(folder_path=temp_dir, is_recursive=False)

        # Check that only the valid function was registered
        assert func_registry.has_function("read_file_content"), "read_file_content should be registered"
        assert not func_registry.has_function("invalid_function_wrong_param_name"), "invalid_function_wrong_param_name should not be registered"
        assert not func_registry.has_function("invalid_function_wrong_param_type"), "invalid_function_wrong_param_type should not be registered"
        assert not func_registry.has_function("invalid_function_wrong_return_type"), "invalid_function_wrong_return_type should not be registered"
        assert not func_registry.has_function("invalid_function_too_many_params"), "invalid_function_too_many_params should not be registered"

        # Verify we can get the function
        registered_func = func_registry.get_function("read_file_content")
        assert registered_func is not None, "Registered function should be retrievable"
        assert registered_func.__name__ == "read_file_content", "Function name should match"

        print("✅ All tests passed!")
        print(f"✅ Successfully registered function: {registered_func.__name__}")


if __name__ == "__main__":
    test_func_registry_utils()
