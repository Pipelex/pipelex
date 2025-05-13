# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

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

    module_name = file_path[:-3].replace(os.sep, ".")
    module = importlib.import_module(module_name)

    # Add the module to sys.modules to ensure proper imports within the module
    sys.modules[module_name] = module
    return module


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
