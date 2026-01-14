import inspect
from collections.abc import Callable
from typing import Any

from pipelex import log
from pipelex.config import get_config
from pipelex.libraries.func.func_library import FuncLibrary, pipe_func
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    import_module_from_file_if_has_decorated_functions,
)


def register_funcs_in_folder(
    func_library: FuncLibrary,
    folder_path: str,
    force_include_dirs: list[str] | None = None,
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

    The function name is used as the library key (or custom name if provided to decorator).

    Args:
        func_library: The FuncLibrary to register functions into
        folder_path: Path to folder containing Python files
        is_recursive: Whether to search recursively in subdirectories
        force_include_dirs: List of directories to force include even if they are within excluded_dirs.

    """
    python_files = find_files_in_dir(
        dir_path=folder_path,
        pattern="*.py",
        is_recursive=is_recursive,
        excluded_dirs=list(get_config().pipelex.scan_config.excluded_dirs),
        force_include_dirs=force_include_dirs,
    )

    for python_file in python_files:
        _register_funcs_in_file(func_library=func_library, file_path=str(python_file))


def _register_funcs_in_file(
    func_library: FuncLibrary,
    file_path: str,
) -> None:
    """Processes a Python file to find and register eligible @pipe_func decorated functions.

    Uses AST parsing to check if the file contains @pipe_func decorated functions before
    importing. Only functions marked with @pipe_func decorator are registered.

    Args:
        func_library: The FuncLibrary to register functions into
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
        functions_to_register = _find_functions_in_module(func_library, module)

        for func in functions_to_register:
            func_name = _get_function_registration_name(func)
            func_library.register_function(
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


def _find_functions_in_module(
    func_library: FuncLibrary,
    module: Any,
) -> list[Callable[..., Any]]:
    """Finds all @pipe_func decorated functions in a module.

    Only functions marked with @pipe_func decorator are included.
    Full eligibility (signature, return type) will be checked during registration.

    Args:
        func_library: The FuncLibrary used for checking pipe_func markers
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
        if not func_library.is_marked_pipe_func(obj):
            continue

        # Add function - full eligibility will be checked by func_library.register_function
        functions.append(obj)

    return functions


def _get_function_registration_name(func: Callable[..., Any]) -> str:
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
