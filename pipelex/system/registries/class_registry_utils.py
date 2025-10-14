import inspect
import sys
import warnings
from pathlib import Path
from typing import Any

from kajson.kajson_manager import KajsonManager

from pipelex import log
from pipelex.config import get_config
from pipelex.tools.misc.file_utils import find_files_in_dir as base_find_files_in_dir
from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    find_classes_in_module,
    import_module_from_file,
    import_module_from_file_if_has_classes,
)


class ClassRegistryUtils:
    @classmethod
    def register_classes_in_file(
        cls,
        file_path: str,
        base_class: type[Any] | None,
        is_include_imported: bool,
    ) -> None:
        """Processes a Python file to find and register classes."""
        module = import_module_from_file(file_path)

        # Find classes that match criteria
        classes_to_register = find_classes_in_module(
            module=module,
            base_class=base_class,
            include_imported=is_include_imported,
        )

        KajsonManager.get_class_registry().register_classes(classes=classes_to_register)

    @classmethod
    def register_classes_in_folder(
        cls,
        folder_path: str,
        base_class: type[Any] | None = None,
        is_recursive: bool = True,
        is_include_imported: bool = False,
    ) -> None:
        """Registers all classes in Python files within folders that are subclasses of base_class.
        If base_class is None, registers all classes.

        Args:
            folder_path: Path to folder containing Python files
            base_class: Optional base class to filter registerable classes
            is_recursive: Whether to search recursively in subdirectories
            include_imported: Whether to include classes imported from other modules
            is_include_imported: Whether to include classes imported from other modules

        """
        python_files = cls.find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
        )

        for python_file in python_files:
            cls.register_classes_in_file(
                file_path=str(python_file),
                base_class=base_class,
                is_include_imported=is_include_imported,
            )

    @classmethod
    def find_files_in_dir(cls, dir_path: str, pattern: str, is_recursive: bool) -> list[Path]:
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

    @classmethod
    def import_modules_in_folder(
        cls,
        folder_path: str,
        is_recursive: bool = True,
        base_class_names: list[str] | None = None,
    ) -> None:
        """Import Python modules without registering their classes.

        This loads modules into sys.modules so their classes are available
        for discovery by auto_register_all_subclasses().

        If base_class_names is provided, uses AST parsing to first check if files
        contain relevant classes before importing them. This avoids executing module-level
        code in files that don't contain the classes you're looking for.

        Args:
            folder_path: Path to folder containing Python files
            is_recursive: Whether to search recursively in subdirectories
            base_class_names: Optional list of base class names (e.g. ["StructuredContent"]).
                            If provided, only imports files that contain classes inheriting
                            from these base classes. If None, imports all Python files.

        """
        python_files = cls.find_files_in_dir(
            dir_path=folder_path,
            pattern="*.py",
            is_recursive=is_recursive,
        )

        for python_file in python_files:
            try:
                if base_class_names is not None:
                    # Use AST-based import to avoid executing modules without relevant classes
                    import_module_from_file_if_has_classes(
                        str(python_file),
                        base_class_names=base_class_names,
                    )
                else:
                    # Import all modules regardless of content
                    import_module_from_file(str(python_file))
            except ModuleFileError:
                # Expected: file validation issues (directories with .py extension, etc.)
                # log.debug(f"Skipping file {python_file}: {e}")
                pass
            except ImportError:
                # Common: missing dependencies, circular imports, relative imports
                # log.debug(f"Could not import {python_file}: {e}"
                pass
            except SyntaxError as exc:
                # Potentially problematic: invalid Python syntax may indicate broken code
                log.warning(f"Syntax error in {python_file}: {exc}")

    @classmethod
    def auto_register_all_subclasses(
        cls,
        base_class: type[Any],
    ) -> int:
        """Scan all loaded modules in sys.modules and register all subclasses of base_class.

        This enables auto-discovery of classes that are already in memory,
        making them available to concepts without explicit registration.

        Args:
            base_class: Base class to filter by (e.g., StructuredContent)

        Returns:
            Number of classes registered

        """
        registered_count = 0
        class_registry = KajsonManager.get_class_registry()

        # Create a snapshot of modules to avoid "dictionary changed size during iteration" error
        # (inspect.getmembers can trigger imports which modify sys.modules)
        modules_snapshot = list(sys.modules.values())

        # Iterate through all loaded modules
        for module in modules_snapshot:
            try:
                # Suppress all warnings during inspection (deprecation warnings from dependencies)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # Find all classes in this module
                    for _, obj in inspect.getmembers(module, inspect.isclass):
                        # Check if it's a subclass of base_class (but not the base_class itself)
                        if obj is not base_class and issubclass(obj, base_class):
                            # Register if not already registered
                            if not class_registry.has_class(name=obj.__name__):
                                class_registry.register_class(obj)
                                registered_count += 1
            except (AttributeError, ImportError, TypeError):
                # Expected: some modules in sys.modules can't be inspected
                # - Built-in/native modules (ImportError)
                # - Modules without expected attributes (AttributeError)
                # - Non-module objects (TypeError)
                pass

        return registered_count
