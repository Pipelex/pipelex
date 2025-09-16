import inspect
from pathlib import Path
from typing import Any, Callable, List, get_type_hints

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.func_registry import func_registry
from pipelex.tools.typing.module_inspector import import_module_from_file


class FuncRegistryUtils:
    @classmethod
    def register_funcs_in_folder(
        cls,
        folder_path: str,
        is_recursive: bool = True,
    ) -> None:
        """
        Registers all functions in Python files within a folder that have:
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
    def _find_functions_in_module(cls, module: Any) -> List[Callable[..., Any]]:
        """
        Finds all functions in a module that match the criteria:
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        """
        functions: List[Callable[..., Any]] = []
        module_name = module.__name__

        # Find all functions in the module (not imported ones)
        for _, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != module_name:
                continue

            if cls._is_eligible_function(obj):
                functions.append(obj)

        return functions

    @classmethod
    def _is_eligible_function(cls, func: Callable[..., Any]) -> bool:
        """
        Checks if a function matches the criteria:
        - Exactly 1 parameter named "working_memory" with type WorkingMemory
        - Return type that is a subclass of StuffContent
        """
        try:
            # Get function signature
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            # Check parameter count and name
            if len(params) != 1:
                return False

            param = params[0]
            if param.name != "working_memory":
                return False

            # Get type hints
            type_hints = get_type_hints(func)

            # Check parameter type
            if "working_memory" not in type_hints:
                return False

            param_type = type_hints["working_memory"]
            if param_type != WorkingMemory:
                return False

            # Check return type
            if "return" not in type_hints:
                return False

            return_type = type_hints["return"]

            # Check if return type is a subclass of StuffContent
            try:
                if inspect.isclass(return_type) and issubclass(return_type, StuffContent):
                    return True
                # Handle generic types like ListContent[SomeType]
                if hasattr(return_type, "__origin__"):
                    origin = getattr(return_type, "__origin__")
                    if inspect.isclass(origin) and issubclass(origin, StuffContent):
                        return True
            except TypeError:
                # Handle cases where issubclass fails on generic types
                pass

            return False

        except Exception:
            # If we can't analyze the function, skip it
            return False

    @classmethod
    def _find_files_in_dir(cls, dir_path: str, pattern: str, is_recursive: bool) -> List[Path]:
        """
        Find files matching a pattern in a directory.

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
        else:
            return list(path.glob(pattern))
