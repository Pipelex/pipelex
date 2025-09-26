import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipelex.tools.func_registry import func_registry
from pipelex.tools.typing.module_inspector import import_module_from_file


class FuncRegistryUtils:
    @classmethod
    def register_funcs_in_folder(
        cls,
        folder_path: str,
        is_recursive: bool = True,
    ) -> None:
        """Discovers and attempts to register all functions in Python files within a folder.
        Only functions that meet the eligibility criteria will be registered:
        - Must be an async function
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent

        The function name is used as the registry key.

        Args:
            folder_path: Path to folder containing Python files
            is_recursive: Whether to search recursively in subdirectories

        """
        python_files = cls._find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
        )

        for python_file in python_files:
            cls._register_funcs_in_file(file_path=str(python_file))

    @classmethod
    def _register_funcs_in_file(cls, file_path: str) -> None:
        """Processes a Python file to find and register eligible functions."""
        try:
            module = import_module_from_file(file_path)

            # Find functions that match criteria
            functions_to_register = cls._find_functions_in_module(module)

            for func in functions_to_register:
                func_registry.register_function(
                    func=func,
                    name=func.__name__,
                    should_warn_if_already_registered=True,
                )
        except Exception as e:
            # Log error but continue processing other files
            print(f"Error processing file {file_path}: {e}")

    @classmethod
    def _find_functions_in_module(cls, module: Any) -> list[Callable[..., Any]]:
        """Finds all functions in a module (eligibility will be checked during registration)."""
        functions: list[Callable[..., Any]] = []
        module_name = module.__name__

        # Find all functions in the module (not imported ones)
        for _, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != module_name:
                continue

            # Add all functions - eligibility will be checked by func_registry.register_function
            functions.append(obj)

        return functions

    @classmethod
    def _find_files_in_dir(cls, dir_path: str, pattern: str, is_recursive: bool) -> list[Path]:
        """Find files matching a pattern in a directory.

        Args:
            dir_path: Directory path to search in
            pattern: File pattern to match (e.g. "*.py")
            is_recursive: Whether to search recursively in subdirectories

        Returns:
            List of matching Path objects

        """
        path = Path(dir_path)
        if is_recursive:
            return list(path.rglob(pattern))
        return list(path.glob(pattern))
