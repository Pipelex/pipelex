import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any


class ModuleFileError(Exception):
    """Exception raised for errors related to module file operations."""


def import_module_from_file(file_path: str) -> Any:
    """Imports a module from a file path.

    Args:
        file_path: Path to the Python file to import

    Returns:
        The imported module

    Raises:
        ModuleFileError: If the file is not a Python file or cannot be loaded

    """
    # Validate that the file is a Python file
    if not file_path.endswith(".py"):
        msg = f"File {file_path} is not a Python file (must end with .py)"
        raise ModuleFileError(msg)

    # Validate that the path exists and is a file, not a directory
    path = Path(file_path)
    if path.exists() and not path.is_file():
        msg = f"Path {file_path} exists but is not a file (it may be a directory)"
        raise ModuleFileError(msg)

    # Convert file path to module-style path to use as the actual module name
    module_name = _convert_file_path_to_module_path(file_path)

    # Check if module is already loaded to avoid duplicate loading
    if module_name in sys.modules:
        return sys.modules[module_name]

    # Use importlib.util to load the module from file path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        msg = f"Could not load module from {file_path}"
        raise ModuleFileError(msg)

    module = importlib.util.module_from_spec(spec)

    # Add the module to sys.modules to ensure proper imports within the module
    sys.modules[module_name] = module

    # Execute the module
    spec.loader.exec_module(module)

    return module


def _convert_file_path_to_module_path(file_path: str) -> str:
    """Convert a file path to a valid module identifier.

    The module name doesn't need to match the actual package structure since
    we're using spec_from_file_location - it just needs to be a unique, valid
    Python identifier for registration in sys.modules.

    Args:
        file_path: Path to the Python file

    Returns:
        A unique, valid Python module name derived from the absolute file path
    """
    # Convert to absolute path for uniqueness and consistency
    abs_path = os.path.abspath(file_path)

    # Remove .py extension
    module_path = abs_path.removesuffix(".py")

    # Replace all non-alphanumeric characters with underscores to create a valid identifier
    # This handles path separators, dots, hyphens, spaces, etc.
    valid_chars: list[str] = []
    for char in module_path:
        if char.isalnum():
            valid_chars.append(char)
        else:
            valid_chars.append("_")

    result = "".join(valid_chars)

    # Ensure it doesn't start with a number (Python requirement)
    if result and result[0].isdigit():
        result = "_" + result

    # Handle edge case of empty result
    if not result:
        msg = f"Cannot create valid module name from file path: {file_path}"
        raise ModuleFileError(msg)

    return result


def find_classes_in_module(
    module: Any,
    base_class: type[Any] | None,
    include_imported: bool,
) -> list[type[Any]]:
    """Finds all classes in a module that match the criteria.

    Args:
        module: The module to search for classes
        base_class: Optional base class to filter classes: will only return classes that are subclasses of this base_class
        include_imported: Whether to include classes imported from other modules

    Returns:
        List of class types that match the criteria

    """
    classes: list[type[Any]] = []
    module_name = module.__name__

    # Find all classes in the module
    for _, obj in inspect.getmembers(module, inspect.isclass):
        # Skip classes that are imported from other modules
        if not include_imported and obj.__module__ != module_name:
            continue

        # Add the class if it's a subclass of base_class or if base_class is None
        if base_class is None or issubclass(obj, base_class):
            classes.append(obj)

    return classes
