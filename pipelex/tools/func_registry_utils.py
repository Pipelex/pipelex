import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipelex import log
from pipelex.tools.func_registry import func_registry
from pipelex.tools.misc.file_utils import find_files_in_dir as base_find_files_in_dir
from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    import_module_from_file,
    import_module_from_file_if_has_decorated_functions,
)


class FuncRegistryUtils:
    @classmethod
    def register_funcs_in_folder(
        cls,
        folder_path: str,
        is_recursive: bool = True,
        decorator_names: list[str] | None = None,
        require_decorator: bool = False,
    ) -> None:
        """Discovers and attempts to register all functions in Python files within a folder.
        Only functions that meet the eligibility criteria will be registered:
        - Must be an async function
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        - Optionally must be marked with a decorator (if decorator_names provided)

        If decorator_names is provided, uses AST parsing to first check if files
        contain decorated functions before importing them. This avoids executing
        module-level code in files that don't contain the functions you're looking for.

        The function name is used as the registry key.

        Args:
            folder_path: Path to folder containing Python files
            is_recursive: Whether to search recursively in subdirectories
            decorator_names: Optional list of decorator names (e.g. ["pipe_func"]).
                           If provided, only imports files that contain functions with these decorators.
                           If None, imports all Python files.
            require_decorator: If True, only functions with decorators in decorator_names are registered.
                             Only used if decorator_names is provided.

        """
        python_files = cls._find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
        )

        for python_file in python_files:
            cls._register_funcs_in_file(
                file_path=str(python_file),
                decorator_names=decorator_names,
                require_decorator=require_decorator,
            )

    @classmethod
    def _register_funcs_in_file(
        cls,
        file_path: str,
        decorator_names: list[str] | None = None,
        require_decorator: bool = False,
    ) -> None:
        """Processes a Python file to find and register eligible functions.

        Args:
            file_path: Path to the Python file
            decorator_names: Optional list of decorator names to filter by
            require_decorator: If True, only functions with the specified decorators are registered

        """
        try:
            # Import the module (potentially with AST pre-check if decorator_names provided)
            if decorator_names is not None:
                module = import_module_from_file_if_has_decorated_functions(
                    file_path,
                    decorator_names=decorator_names,
                )
                # If no decorated functions found, module will be None
                if module is None:
                    return
            else:
                module = import_module_from_file(file_path)

            # Find functions that match criteria
            functions_to_register = cls._find_functions_in_module(
                module,
                require_decorator=require_decorator,
            )

            for func in functions_to_register:
                # Check for custom name from decorator
                custom_name = getattr(func, "_pipe_func_name", None)
                func_name = custom_name if custom_name is not None else func.__name__

                func_registry.register_function(
                    func=func,
                    name=func_name,
                    should_warn_if_already_registered=True,
                )
        except ModuleFileError:
            # Expected: file validation issues (directories with .py extension, etc.)
            # log.verbose(f"Skipping file {file_path}: {e}")
            pass
        except ImportError:
            # Common: missing dependencies, circular imports, relative imports
            # log.verbose(f"Could not import {file_path}: {e}")
            pass
        except SyntaxError as exc:
            # Potentially problematic: invalid Python syntax may indicate broken code
            log.warning(f"Syntax error in {file_path}: {exc}")

    @classmethod
    def _find_functions_in_module(
        cls,
        module: Any,
        require_decorator: bool = False,
    ) -> list[Callable[..., Any]]:
        """Finds all functions in a module (eligibility will be checked during registration).

        Args:
            module: The module to search for functions
            require_decorator: If True, only functions marked with @pipe_func are included

        Returns:
            List of functions found in the module

        """
        functions: list[Callable[..., Any]] = []
        module_name = module.__name__

        # Find all functions in the module (not imported ones)
        for _, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != module_name:
                continue

            # If decorator is required, check for it
            if require_decorator and not func_registry.is_marked_pipe_func(obj):
                continue

            # Add function - full eligibility will be checked by func_registry.register_function
            functions.append(obj)

        return functions

    @classmethod
    def _find_files_in_dir(cls, dir_path: str, pattern: str, is_recursive: bool) -> list[Path]:
        """Find files matching a pattern in a directory, excluding common build/cache directories.

        Args:
            dir_path: Directory path to search in
            pattern: File pattern to match (e.g. "*.py")
            is_recursive: Whether to search recursively in subdirectories

        Returns:
            List of matching Path objects, filtered to exclude problematic directories

        """
        # Get all files using the base utility
        all_files = base_find_files_in_dir(dir_path, pattern, is_recursive)

        # Directories to exclude from scanning to avoid import issues
        exclude_dirs = {".venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".env", "results"}

        # Filter out files in excluded directories
        filtered_files: list[Path] = []
        for file_path in all_files:
            # Check if any parent directory is in the exclude list
            should_exclude = any(part in exclude_dirs for part in file_path.parts)
            if not should_exclude:
                filtered_files.append(file_path)

        return filtered_files
