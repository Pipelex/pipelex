import importlib
import inspect
import pkgutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipelex import log
from pipelex.config import get_config
from pipelex.system.registries.func_registry import func_registry, pipe_func
from pipelex.tools.misc.file_utils import find_files_in_dir as base_find_files_in_dir
from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    import_module_from_file_if_has_decorated_functions,
)


class FuncRegistryUtils:
    @classmethod
    def register_pipe_funcs_from_package(cls, package_name: str, package: Any) -> int:
        """Register all @pipe_func decorated functions from a package.

        Args:
            package_name: Full name of the package (e.g. "pipelex.builder")
            package: The imported package object

        Returns:
            Number of functions registered

        """
        functions_registered = 0

        if not hasattr(package, "__path__"):
            log.warning(f"Package {package_name} has no __path__ attribute, cannot walk modules")
            return 0

        log.verbose(f"Walking package {package_name} at {package.__path__}")

        for _importer, modname, _ispkg in pkgutil.walk_packages(
            path=package.__path__,
            prefix=f"{package_name}.",
            onerror=lambda _: None,
        ):
            # Import the module
            module = importlib.import_module(modname)
            log.verbose(f"Imported {modname}")

            # Find @pipe_func decorated functions in this module
            functions_to_register = cls._find_functions_in_module(module)

            for func in functions_to_register:
                func_name = cls._get_function_registration_name(func)
                func_registry.register_function(
                    func=func,
                    name=func_name,
                )
                functions_registered += 1
                log.verbose(f"Registered @pipe_func: {func_name} from {modname}")

        return functions_registered

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
        - Must be marked with the @pipe_func decorator

        Uses AST parsing to first check if files contain @pipe_func decorated functions
        before importing them. This avoids executing module-level code in files that
        don't contain the functions you're looking for.

        The function name is used as the registry key (or custom name if provided to decorator).

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
    def _register_funcs_in_file(
        cls,
        file_path: str,
    ) -> None:
        """Processes a Python file to find and register eligible @pipe_func decorated functions.

        Uses AST parsing to check if the file contains @pipe_func decorated functions before
        importing. Only functions marked with @pipe_func decorator are registered.

        Args:
            file_path: Path to the Python file

        """
        try:
            # Import the module only if it has @pipe_func decorated functions
            module = import_module_from_file_if_has_decorated_functions(
                file_path,
                decorator_names=[pipe_func.__name__],
            )
            # If no decorated functions found, module will be None
            if module is None:
                return

            # Find functions that match criteria
            functions_to_register = cls._find_functions_in_module(module)

            for func in functions_to_register:
                func_name = cls._get_function_registration_name(func)
                func_registry.register_function(
                    func=func,
                    name=func_name,
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
    ) -> list[Callable[..., Any]]:
        """Finds all @pipe_func decorated functions in a module.

        Only functions marked with @pipe_func decorator are included.
        Full eligibility (signature, return type) will be checked during registration.

        Args:
            module: The module to search for functions

        Returns:
            List of @pipe_func decorated functions found in the module

        """
        functions: list[Callable[..., Any]] = []
        module_name = module.__name__

        # Find all functions in the module (not imported ones)
        for _, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != module_name:
                continue

            # Only include functions marked with @pipe_func
            if not func_registry.is_marked_pipe_func(obj):
                continue

            # Add function - full eligibility will be checked by func_registry.register_function
            functions.append(obj)

        return functions

    @classmethod
    def _get_function_registration_name(cls, func: Callable[..., Any]) -> str:
        """Extract the registration name for a function.

        If the function has a custom name from the @pipe_func decorator, use that.
        Otherwise, use the function's __name__.

        Args:
            func: The function to get the registration name for

        Returns:
            The name to use when registering the function

        """
        custom_name = getattr(func, "_pipe_func_name", None)
        return custom_name if custom_name is not None else func.__name__

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

        # Filter out files in excluded directories
        filtered_files: list[Path] = []
        excluded_dirs = get_config().pipelex.scan_config.excluded_dirs
        for file_path in all_files:
            # Check if any parent directory is in the exclude list
            should_exclude = any(part in excluded_dirs for part in file_path.parts)
            if not should_exclude:
                filtered_files.append(file_path)

        return filtered_files
