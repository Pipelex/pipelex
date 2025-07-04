from pathlib import Path
from typing import Any, List, Optional, Type

from pipelex.hub import get_class_registry
from pipelex.tools.typing.module_inspector import find_classes_in_module, import_module_from_file


class ClassRegistryUtils:
    @classmethod
    def register_classes_in_file(
        cls,
        file_path: str,
        base_class: Optional[Type[Any]],
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

        get_class_registry().register_classes(classes=classes_to_register)

    @classmethod
    def register_classes_in_folder(
        cls,
        folder_path: str,
        base_class: Optional[Type[Any]] = None,
        is_recursive: bool = True,
        is_include_imported: bool = False,
    ) -> None:
        """
        Registers all classes in Python files within folders that are subclasses of base_class.
        If base_class is None, registers all classes.

        Args:
            folder_paths: List of paths to folders containing Python files
            base_class: Optional base class to filter registerable classes
            recursive: Whether to search recursively in subdirectories
            exclude_files: List of filenames to exclude
            exclude_dirs: List of directory names to exclude
            include_imported: Whether to include classes imported from other modules
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
    def find_files_in_dir(cls, dir_path: str, pattern: str, is_recursive: bool) -> List[Path]:
        """
        Find files matching a pattern in a directory.

        Args:
            dir_path: Directory path to search in
            pattern: File pattern to match (e.g. "*.py")
            recursive: Whether to search recursively in subdirectories

        Returns:
            List of matching Path objects
        """
        path = Path(dir_path)
        if is_recursive:
            return list(path.rglob(pattern))
        else:
            return list(path.glob(pattern))
