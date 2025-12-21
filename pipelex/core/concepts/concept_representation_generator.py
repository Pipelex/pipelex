"""Generator for concept representation values in JSON and Python formats.

This module provides recursive generation of example representations for concept structures.
It supports two output formats: JSON (dict) and Python (class instantiation strings).
"""

import inspect
from typing import Any, cast, get_args, get_origin

from pydantic import BaseModel

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.types import StrEnum


class ConceptRepresentationFormat(StrEnum):
    """Output format for concept representations."""

    JSON = "json"
    PYTHON = "python"


class ConceptRepresentationGenerator:
    """Generates representation values for concepts in different formats.

    Supports two output formats (JSON and Python).
    The generation is recursive: nested StuffContent classes are fully expanded.

    JSON format:
        {"concept": "domain.ConceptCode", "content": {"field1": "value1", ...}}

    Python format:
        {"concept": "domain.ConceptCode", "content": "MyClass(field1='value1', ...)"}
    """

    def __init__(self, output_format: ConceptRepresentationFormat):
        self.output_format = output_format
        self._imports_needed: set[str] = set()

    @property
    def imports_needed(self) -> set[str]:
        """Returns the set of class names that need to be imported."""
        return self._imports_needed

    def generate_representation(
        self,
        concept_ref: str,
        structure_class: type[StuffContent],
        include_optional: bool = True,
    ) -> dict[str, Any]:
        """Generate a representation value for a concept.

        This is the main entry point. It wraps the generated content with concept.

        Args:
            concept_ref: The concept string (e.g., "domain.ConceptCode")
            structure_class: The StuffContent class to generate representation for
            include_optional: If False, exclude fields with default values (optional fields)

        Returns:
            Dict with concept and content keys
        """
        self._imports_needed.clear()

        content = self.generate_class_representation(structure_class, include_optional=include_optional)

        return {"concept": concept_ref, "content": content}

    def generate_class_representation(
        self,
        content_class: type[StuffContent],
        include_optional: bool = True,
    ) -> dict[str, Any] | str:
        """Generate representation for a StuffContent class (recursive).

        For JSON format: returns a dict with all fields
        For Python format: returns a string like "ClassName(field1=..., field2=...)"

        Args:
            content_class: The StuffContent class to generate representation for
            include_optional: If False, exclude fields with default values (optional fields)

        Returns:
            Dict (JSON) or string (Python) representing the class
        """
        class_name = content_class.__name__
        self._imports_needed.add(class_name)

        fields_dict = self._generate_fields_dict(content_class, include_optional=include_optional)

        match self.output_format:
            case ConceptRepresentationFormat.JSON:
                return fields_dict
            case ConceptRepresentationFormat.PYTHON:
                return self._format_as_python(class_name, fields_dict)

    def _generate_fields_dict(
        self,
        content_class: type[StuffContent],
        include_optional: bool = True,
    ) -> dict[str, Any]:
        """Generate a dict with field values for a class.

        Args:
            content_class: The class to generate fields for
            include_optional: If False, exclude fields with default values (optional fields)

        Returns:
            Dict mapping field names to their generated values
        """
        fields_dict: dict[str, Any] = {}

        for field_name, field_info in content_class.model_fields.items():
            # Skip optional fields if include_optional is False
            if not include_optional and not field_info.is_required():
                continue

            field_type = field_info.annotation
            field_value = self.generate_field_value(field_type, field_name)
            fields_dict[field_name] = field_value

        return fields_dict

    def generate_field_value(self, field_type: Any, field_name: str) -> Any:
        """Generate a representation value for a field based on its type (recursive).

        Handles:
        - Basic types (str, int, float, bool)
        - StrEnum types (returns first enum value)
        - list[T] types (recursively generates item)
        - dict types (generates placeholder)
        - Nested StuffContent/BaseModel classes (recursive call)

        Args:
            field_type: The type annotation of the field
            field_name: Name of the field (used for generating placeholder values)

        Returns:
            Generated value appropriate for the field type
        """
        actual_type = self._unwrap_optional(field_type)
        origin = get_origin(actual_type)
        args = get_args(actual_type)

        # Handle list types
        if origin is list:
            return self._generate_list_value(args, field_name)

        # Handle dict types
        if origin is dict:
            return self._generate_dict_value(field_name)

        # Handle StrEnum types
        if inspect.isclass(actual_type) and issubclass(actual_type, StrEnum):
            return self._generate_enum_value(actual_type, field_name)

        # Handle nested StuffContent (recursive)
        if inspect.isclass(actual_type) and issubclass(actual_type, StuffContent):
            return self.generate_class_representation(actual_type)

        # Handle nested BaseModel that is NOT StuffContent
        if inspect.isclass(actual_type) and issubclass(actual_type, BaseModel):
            return self._generate_basemodel_representation(actual_type)

        # Handle basic types
        return self._generate_basic_value(actual_type, field_name)

    def _unwrap_optional(self, field_type: Any) -> Any:
        """Unwrap Optional[T] to get T.

        Args:
            field_type: The type to unwrap

        Returns:
            The inner type if Optional, otherwise the original type
        """
        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin is type(None) or (args and type(None) in args):
            return next((arg for arg in args if arg is not type(None)), field_type) if args else field_type
        return field_type

    def _generate_list_value(self, args: tuple[Any, ...], field_name: str) -> list[Any]:
        """Generate a list value with one example item.

        Args:
            args: Type arguments of the list (e.g., (str,) for list[str])
            field_name: Name of the field

        Returns:
            List with one generated item
        """
        if not args:
            return [f"{field_name}_item"]

        item_type = args[0]

        # Handle list of StuffContent (recursive)
        if inspect.isclass(item_type) and issubclass(item_type, StuffContent):
            item_repr = self.generate_class_representation(item_type)
            return [item_repr]

        # Handle list of BaseModel (not StuffContent)
        if inspect.isclass(item_type) and issubclass(item_type, BaseModel):
            item_repr = self._generate_basemodel_representation(item_type)
            return [item_repr]

        # Handle list of basic types
        return [self._generate_basic_value(item_type, f"{field_name}_item")]

    def _generate_dict_value(self, field_name: str) -> dict[str, str]:
        """Generate a placeholder dict value.

        Args:
            field_name: Name of the field

        Returns:
            Dict with placeholder key/value
        """
        return {f"{field_name}_key": f"{field_name}_value"}

    def _generate_enum_value(self, enum_type: type[StrEnum], field_name: str) -> str:
        """Generate a value from a StrEnum type.

        Args:
            enum_type: The StrEnum class
            field_name: Name of the field (used as fallback)

        Returns:
            First enum value or placeholder if empty
        """
        enum_values = list(enum_type)
        return enum_values[0].value if enum_values else f"{field_name}_enum"

    def _generate_basemodel_representation(self, model_class: type[BaseModel]) -> dict[str, Any] | str:
        """Generate representation for a BaseModel that is not StuffContent.

        Args:
            model_class: The BaseModel class

        Returns:
            Dict (JSON) or string (Python)
        """
        class_name = model_class.__name__
        self._imports_needed.add(class_name)

        fields_dict: dict[str, Any] = {}
        for field_name, field_info in model_class.model_fields.items():
            field_type = field_info.annotation
            field_value = self.generate_field_value(field_type, field_name)
            fields_dict[field_name] = field_value

        match self.output_format:
            case ConceptRepresentationFormat.JSON:
                return fields_dict
            case ConceptRepresentationFormat.PYTHON:
                return self._format_as_python(class_name, fields_dict)

    def _generate_basic_value(self, actual_type: Any, field_name: str) -> Any:
        """Generate a value for basic Python types.

        Args:
            actual_type: The type (str, int, float, bool, or unknown)
            field_name: Name of the field (used for generating placeholder)

        Returns:
            Appropriate placeholder value for the type
        """
        if actual_type is str:
            return f"{field_name}_value"
        elif actual_type is int:
            return 0
        elif actual_type is float:
            return 0.0
        elif actual_type is bool:
            return False
        else:
            type_name = getattr(actual_type, "__name__", str(actual_type))
            return f"{field_name}_{type_name}"

    def _format_as_python(self, class_name: str, fields: dict[str, Any]) -> str:
        """Format a class instantiation as Python code string.

        Args:
            class_name: Name of the class
            fields: Dict of field names to values

        Returns:
            String like "ClassName(field1=..., field2=...)"
        """
        args_parts: list[str] = []
        for field_name, value in fields.items():
            formatted_value = self._format_python_value(value)
            args_parts.append(f"{field_name}={formatted_value}")

        args = ", ".join(args_parts)
        return f"{class_name}({args})"

    def _format_python_value(self, value: Any) -> str:
        """Format a value for Python code representation.

        Args:
            value: The value to format

        Returns:
            Python code string representation

        Examples:
            >>> self._format_python_value("hello")
            '"hello"'
            >>> self._format_python_value("MyClass(arg=value)")  # Already a Python expression
            'MyClass(arg=value)'
            >>> self._format_python_value(True)
            'True'
            >>> self._format_python_value(42)
            '42'
            >>> self._format_python_value(3.14)
            '3.14'
            >>> self._format_python_value({"key": "val"})
            '{"key": "val"}'
            >>> self._format_python_value([1, 2, 3])
            '[1, 2, 3]'
        """
        if isinstance(value, str):
            # Check if it's already a Python expression (class instantiation)
            if "(" in value and ")" in value and "=" in value:
                return value
            return f'"{value}"'
        elif isinstance(value, (bool, int, float)):
            return str(value)
        elif isinstance(value, dict):
            dict_value = cast("dict[str, Any]", value)
            items = ", ".join(f"{self._format_python_value(key)}: {self._format_python_value(val)}" for key, val in dict_value.items())
            return "{" + items + "}"
        elif isinstance(value, list):
            list_value = cast("list[Any]", value)
            items = ", ".join(self._format_python_value(item) for item in list_value)
            return "[" + items + "]"
        else:
            return str(value)


# Convenience functions


def generate_json_representation(
    concept_ref: str,
    structure_class: type[StuffContent],
) -> dict[str, Any]:
    """Convenience function to generate a JSON format representation.

    Args:
        concept_ref: The concept string (e.g., "domain.ConceptCode")
        structure_class: The StuffContent class

    Returns:
        Dict with concept and content
    """
    generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
    return generator.generate_representation(concept_ref, structure_class)


def generate_python_representation(
    concept_ref: str,
    structure_class: type[StuffContent],
) -> tuple[dict[str, Any], set[str]]:
    """Convenience function to generate a Python format representation.

    Args:
        concept_ref: The concept string (e.g., "domain.ConceptCode")
        structure_class: The StuffContent class

    Returns:
        Tuple of (representation dict, imports_needed set)
    """
    generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
    representation = generator.generate_representation(concept_ref, structure_class)
    return representation, generator.imports_needed
