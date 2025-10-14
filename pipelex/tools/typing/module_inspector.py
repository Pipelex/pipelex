import ast
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
    module_name = convert_file_path_to_module_path(file_path)

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


def convert_file_path_to_module_path(file_path: str) -> str:
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


def find_class_names_in_file(file_path: str, base_class_names: list[str] | None = None) -> list[str]:
    """Find class names in a Python file without executing it using AST parsing.

    This is useful when you want to discover classes without running module-level code.

    Args:
        file_path: Path to the Python file to analyze
        base_class_names: Optional list of base class names to filter by.
                         Only returns classes that inherit from these bases.
                         If None, returns all class definitions.

    Returns:
        List of class names found in the file

    Raises:
        ModuleFileError: If the file cannot be read or parsed

    """
    # Validate that the file is a Python file
    if not file_path.endswith(".py"):
        msg = f"File {file_path} is not a Python file (must end with .py)"
        raise ModuleFileError(msg)

    # Validate that the path exists and is a file
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        msg = f"Path {file_path} does not exist or is not a file"
        raise ModuleFileError(msg)

    try:
        # Read and parse the file
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except Exception as e:
        msg = f"Failed to parse {file_path}: {e}"
        raise ModuleFileError(msg) from e

    class_names: list[str] = []

    # Walk through the AST to find class definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # If no base class filter, add all classes
            if base_class_names is None:
                class_names.append(node.name)
                continue

            # Check if this class inherits from any of the specified base classes
            for base in node.bases:
                # Handle simple names like "StructuredContent"
                if isinstance(base, ast.Name) and base.id in base_class_names:
                    class_names.append(node.name)
                    break
                # Handle attribute access like "pipelex.StructuredContent"
                if isinstance(base, ast.Attribute):
                    if base.attr in base_class_names:
                        class_names.append(node.name)
                        break

    return class_names


def find_decorated_function_names_in_file(
    file_path: str,
    decorator_names: list[str],
) -> list[str]:
    """Find function names decorated with specific decorators without executing the file.

    This uses AST parsing to find functions with specific decorators.

    Args:
        file_path: Path to the Python file to analyze
        decorator_names: List of decorator names to look for (e.g. ["pipe_func", "register_func"])

    Returns:
        List of function names that have the specified decorators

    Raises:
        ModuleFileError: If the file cannot be read or parsed

    """
    # Validate that the file is a Python file
    if not file_path.endswith(".py"):
        msg = f"File {file_path} is not a Python file (must end with .py)"
        raise ModuleFileError(msg)

    # Validate that the path exists and is a file
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        msg = f"Path {file_path} does not exist or is not a file"
        raise ModuleFileError(msg)

    try:
        # Read and parse the file
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except Exception as e:
        msg = f"Failed to parse {file_path}: {e}"
        raise ModuleFileError(msg) from e

    function_names: list[str] = []

    # Walk through the AST to find function definitions with decorators
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if function has any of the specified decorators
            for decorator in node.decorator_list:
                decorator_name = None

                # Handle simple decorator names like @pipe_func
                if isinstance(decorator, ast.Name):
                    decorator_name = decorator.id
                # Handle decorator calls like @pipe_func() or @pipe_func(name="foo")
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name):
                        decorator_name = decorator.func.id
                    # Handle qualified names like @registry.pipe_func()
                    elif isinstance(decorator, ast.Attribute):
                        decorator_name = decorator.attr

                if decorator_name in decorator_names:
                    function_names.append(node.name)
                    break  # Found a matching decorator, no need to check others

    return function_names


def import_module_from_file_if_has_decorated_functions(
    file_path: str,
    decorator_names: list[str],
) -> Any | None:
    """Import a module only if it contains functions with specific decorators.

    This function uses AST parsing to check if the file contains functions decorated
    with specific decorators before importing, avoiding execution of modules that don't
    have the functions you're looking for.

    Args:
        file_path: Path to the Python file to potentially import
        decorator_names: List of decorator names to look for (e.g. ["pipe_func"])

    Returns:
        The imported module if it contains decorated functions, None otherwise

    Raises:
        ModuleFileError: If the file is not a Python file or cannot be loaded

    """
    # First, use AST to check if file has decorated functions
    function_names = find_decorated_function_names_in_file(file_path, decorator_names)

    # If no decorated functions found, skip import
    if not function_names:
        return None

    # File has decorated functions, import it
    return import_module_from_file(file_path)


def import_module_from_file_if_has_classes(
    file_path: str,
    base_class_names: list[str] | None = None,
) -> Any | None:
    """Import a module only if it contains classes (optionally filtered by base class).

    This function uses AST parsing to check if the file contains relevant classes
    before importing, avoiding execution of modules that don't have the classes
    you're looking for.

    Args:
        file_path: Path to the Python file to potentially import
        base_class_names: Optional list of base class names to filter by.
                         Only imports if file contains classes inheriting from these.
                         If None, imports if file contains any class definitions.

    Returns:
        The imported module if it contains relevant classes, None otherwise

    Raises:
        ModuleFileError: If the file is not a Python file or cannot be loaded

    """
    # First, use AST to check if file has relevant classes
    class_names = find_class_names_in_file(file_path, base_class_names)

    # If no relevant classes found, skip import
    if not class_names:
        return None

    # File has relevant classes, import it
    return import_module_from_file(file_path)


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
