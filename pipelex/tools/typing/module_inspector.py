import importlib.util
import inspect
import os
import sys
from typing import Any, List, Optional, Type


class ModuleFileError(Exception):
    """Exception raised for errors related to module file operations."""

    pass


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
        raise ModuleFileError(f"File {file_path} is not a Python file (must end with .py)")

    # Convert file path to module-style path to use as the actual module name
    module_name = _convert_file_path_to_module_path(file_path)

    # Check if module is already loaded to avoid duplicate loading
    if module_name in sys.modules:
        return sys.modules[module_name]

    # Use importlib.util to load the module from file path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ModuleFileError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)

    # Add the module to sys.modules to ensure proper imports within the module
    sys.modules[module_name] = module

    # Execute the module
    spec.loader.exec_module(module)

    return module


def _convert_file_path_to_module_path(file_path: str) -> str:
    """Convert a file path to a module-style path."""
    # Remove .py extension
    module_path = file_path[:-3] if file_path.endswith(".py") else file_path

    # Replace path separators with dots
    module_path = module_path.replace(os.sep, ".")

    # Handle __init__.py files by removing the __init__ part
    if module_path.endswith(".__init__"):
        module_path = module_path[:-9]

    return module_path


def find_classes_in_module(
    module: Any,
    base_class: Optional[Type[Any]],
    include_imported: bool,
) -> List[Type[Any]]:
    """
    Finds all classes in a module that match the criteria.

    Args:
        module: The module to search for classes
        base_class: Optional base class to filter classes: will only return classes that are subclasses of this base_class
        include_imported: Whether to include classes imported from other modules

    Returns:
        List of class types that match the criteria
    """
    classes: List[Type[Any]] = []
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
