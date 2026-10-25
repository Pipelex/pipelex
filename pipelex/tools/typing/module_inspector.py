import ast
import importlib.util
import inspect
import sys
import threading
from pathlib import Path
from typing import Any

from pipelex.tools.typing.exceptions import ModuleFileError

#: The directories `import_module_from_file` put on `sys.path`, each once, so that whoever unloads the modules of a
#: directory, such as the process's hold on a method tree's Python, takes the entries introduced beneath it off again.
_inserted_module_dirs: list[str] = []


#: Held while `import_module_from_file` publishes a module in `sys.modules` and executes it, and by a library load around
#: its imports and the class discovery that reads them (`LibraryManager.load_libraries`). Method loads run in parallel
#: worker threads, and a module is published before it executes, so without it a second load could take a module half
#: executed, or discover the classes of one, as complete. Reentrant, since a module executing may import another by file.
MODULE_IMPORT_LOCK = threading.RLock()


def import_module_from_file(file_path: Path) -> Any:
    """Imports a module from a file path.

    Args:
        file_path: Path to the Python file to import

    Returns:
        The imported module

    Raises:
        ModuleFileError: If the file is not a Python file or cannot be loaded

    """
    # Validate that the file is a Python file
    if file_path.suffix != ".py":
        msg = f"File {file_path} is not a Python file (must end with .py)"
        raise ModuleFileError(msg)

    # Validate that the path exists and is a file, not a directory
    if file_path.exists() and not file_path.is_file():
        msg = f"Path {file_path} exists but is not a file (it may be a directory)"
        raise ModuleFileError(msg)

    # Convert file path to module-style path to use as the actual module name
    module_name = convert_file_path_to_module_path(file_path)

    # The module is published before it executes, so another thread must not read it until it has: the check, the
    # publication and the execution hold the lock together.
    with MODULE_IMPORT_LOCK:
        # Check if module is already loaded to avoid duplicate loading
        if module_name in sys.modules:
            return sys.modules[module_name]

        # Use importlib.util to load the module from file path
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            msg = f"Could not load module from {file_path}"
            raise ModuleFileError(msg)

        module = importlib.util.module_from_spec(spec)

        # Add the module to sys.modules to ensure proper imports within the module
        sys.modules[module_name] = module

        # Put the file's OWN directory on sys.path so a module imported by path can import its siblings
        # (e.g. `from helpers import ...` between files in the same bundle). Importing via
        # spec_from_file_location does NOT do this automatically — unlike running a script, where the
        # script's directory lands on sys.path[0]. Without it, a top-level sibling import raises
        # ModuleNotFoundError and the module never finishes importing. Deduped, so repeated scans don't
        # grow sys.path unbounded.
        module_dir = str(file_path.resolve().parent)
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
            if module_dir not in _inserted_module_dirs:
                _inserted_module_dirs.append(module_dir)

        # Execute the module. One that fails to execute leaves `sys.modules`, as the import system's own imports do, so a
        # later import executes it again rather than taking the half-executed module as imported.
        executed = False
        try:
            spec.loader.exec_module(module)
            executed = True
        finally:
            if not executed and sys.modules.get(module_name) is module:
                del sys.modules[module_name]

        return module


def drop_module_dirs_inserted_under(*, directory: Path) -> None:
    """Take off `sys.path` every entry `import_module_from_file` put there for a file at or beneath `directory`.

    Args:
        directory: A resolved directory, such as the root of a method tree whose modules are being unloaded.
    """
    for module_dir in list(_inserted_module_dirs):
        if not Path(module_dir).is_relative_to(directory):
            continue
        _inserted_module_dirs.remove(module_dir)
        if module_dir in sys.path:
            sys.path.remove(module_dir)


def convert_file_path_to_module_path(file_path: Path) -> str:
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
    abs_path = str(file_path.resolve())

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


def find_class_names_in_file(file_path: Path, *, base_class_names: list[str] | None = None) -> list[str]:
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
    if file_path.suffix != ".py":
        msg = f"File {file_path} is not a Python file (must end with .py)"
        raise ModuleFileError(msg)

    # Validate that the path exists and is a file
    if not file_path.exists() or not file_path.is_file():
        msg = f"Path {file_path} does not exist or is not a file"
        raise ModuleFileError(msg)

    try:
        # Read and parse the file
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError, ValueError) as exc:
        msg = f"Failed to parse {file_path}: {exc}"
        raise ModuleFileError(msg) from exc

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


def import_module_from_file_if_has_classes(
    file_path: Path,
    *,
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
    class_names = find_class_names_in_file(file_path, base_class_names=base_class_names)

    # If no relevant classes found, skip import
    if not class_names:
        return None

    # File has relevant classes, import it
    return import_module_from_file(file_path)


def find_classes_in_module(
    module: Any,
    *,
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
