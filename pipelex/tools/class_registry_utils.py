from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin

from kajson.kajson_manager import KajsonManager
from pydantic.fields import FieldInfo

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

        KajsonManager.get_class_registry().register_classes(classes=classes_to_register)

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

    @staticmethod
    def are_classes_equivalent(class_1: Type[Any], class_2: Type[Any]) -> bool:
        """Check if two Pydantic classes are equivalent (same fields, types, descriptions)."""
        if not (hasattr(class_1, "model_fields") and hasattr(class_2, "model_fields")):
            return class_1 == class_2

        # Compare model schemas using Pydantic's built-in capabilities
        try:
            schema_1: Dict[str, Any] = class_1.model_json_schema()  # type: ignore[attr-defined]
            schema_2: Dict[str, Any] = class_2.model_json_schema()  # type: ignore[attr-defined]
            return schema_1 == schema_2
        except Exception:
            # Fallback to manual field comparison if schema comparison fails
            fields_1: Dict[str, FieldInfo] = class_1.model_fields  # type: ignore[attr-defined]
            fields_2: Dict[str, FieldInfo] = class_2.model_fields  # type: ignore[attr-defined]

            if set(fields_1.keys()) != set(fields_2.keys()):
                return False

            for field_name in fields_1.keys():
                field_1: FieldInfo = fields_1[field_name]
                field_2: FieldInfo = fields_2[field_name]

                # Compare field types
                if field_1.annotation != field_2.annotation:
                    return False

                # Compare field descriptions if they exist
                if getattr(field_1, "description", None) != getattr(field_2, "description", None):
                    return False

                # Compare default values
                if field_1.default != field_2.default:
                    return False

            return True

    @staticmethod
    def has_compatible_field(class_1: Type[Any], class_2: Type[Any]) -> bool:
        """Check if class_1 has a field that is compatible with class_2."""
        if not hasattr(class_1, "model_fields"):
            return False

        fields: Dict[str, FieldInfo] = class_1.model_fields  # type: ignore[attr-defined]
        for _field_name, field_info in fields.items():
            field_type = field_info.annotation

            # Handle Optional types by extracting the inner type
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                # Check if this is Optional[T] (Union[T, None])
                if len(args) == 2 and type(None) in args:
                    field_type = args[0] if args[1] is type(None) else args[1]

            # Check if the field type matches class_2
            if field_type == class_2:
                return True

            # Check if field_type is a subclass of class_2
            try:
                if isinstance(field_type, type) and issubclass(field_type, class_2):
                    return True
            except TypeError:
                pass

        return False
