"""Generator for concept example values in JSON and Python formats."""

import inspect
from typing import Any, cast, get_args, get_origin

from kajson.kajson_manager import KajsonManager

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.types import StrEnum


class ConceptExampleFormat(StrEnum):
    """Output format for concept examples."""

    JSON = "json"
    PYTHON = "python"


class ConceptExampleGranularity(StrEnum):
    """Granularity level for concept examples.

    LIGHT: Simplified format for simple types
        - TextContent: "my_text"
        - NumberContent: 0
        - ImageContent: {"_class": "ImageContent", "url": "..."}

    HARD: Full BaseModel format with all fields explicitly shown
        - TextContent: {"text": "my_text"}
        - NumberContent: {"value": 0}
        - ImageContent: {"url": "..."}
    """

    LIGHT = "light"
    HARD = "hard"


class ConceptExampleGenerator:
    """Generates example values for concepts in different formats.

    Supports two output formats (JSON and Python) and two granularity levels (Light and Hard).

    JSON format (Light):
        For native.Text: "my_text"
        For structured: {"concept_code": "domain.ConceptCode", "content": {...}}

    JSON format (Hard):
        For native.Text: {"concept_code": "native.Text", "content": {"text": "my_text"}}
        For structured: {"concept_code": "domain.ConceptCode", "content": {...}}

    Python format (Light):
        For native.Text: "my_text"
        For structured: {"concept_code": "domain.ConceptCode", "content": MyClass(field1="value1")}

    Python format (Hard):
        For native.Text: TextContent(text="my_text")
        For structured: {"concept_code": "domain.ConceptCode", "content": MyClass(field1="value1")}
    """

    def __init__(
        self,
        output_format: ConceptExampleFormat,
        granularity: ConceptExampleGranularity = ConceptExampleGranularity.LIGHT,
    ):
        self.output_format = output_format
        self.granularity = granularity
        self._imports_needed: set[str] = set()

    @property
    def imports_needed(self) -> set[str]:
        """Returns the set of class names that need to be imported."""
        return self._imports_needed

    def generate_example(
        self,
        concept_string: str,
        structure_class_name: str,
        var_name: str,
    ) -> dict[str, Any] | str | int:
        """Generate an example value for a concept.

        Args:
            concept_string: The concept string (e.g., "domain.ConceptCode")
            structure_class_name: The name of the structure class
            var_name: Variable name for generating contextual example values

        Returns:
            Example value in the specified format
        """
        self._imports_needed.clear()

        # Get the structure class
        structure_class = KajsonManager.get_class_registry().get_class(name=structure_class_name)

        # If class not found, return placeholder
        if structure_class is None:
            return {"concept_code": concept_string, "content": {}}

        # Verify it's a subclass of StuffContent
        if not issubclass(structure_class, StuffContent):
            return {"concept_code": concept_string, "content": {}}

        # Track this class for imports
        self._imports_needed.add(structure_class_name)

        # Check if this is a native concept
        is_native = NativeConceptCode.is_native_concept_string_or_code(concept_string_or_code=concept_string)

        # Generate content based on format and granularity
        content = self._generate_content_for_class(structure_class, var_name)

        # Handle native concepts
        if is_native:
            return self._handle_native_concept(concept_string, structure_class_name, var_name)

        return {"concept_code": concept_string, "content": content}

    def _handle_native_concept(
        self,
        concept_string: str,
        structure_class_name: str,
        var_name: str,
    ) -> dict[str, Any] | str | int:
        """Handle native concepts based on granularity."""
        match self.granularity:
            case ConceptExampleGranularity.LIGHT:
                return self._handle_native_concept_light(structure_class_name, var_name)
            case ConceptExampleGranularity.HARD:
                return self._handle_native_concept_hard(concept_string, structure_class_name)

    def _handle_native_concept_light(
        self,
        structure_class_name: str,
        var_name: str,
    ) -> dict[str, Any] | str | int:
        """Handle native concepts in LIGHT mode - simplified format."""
        match structure_class_name:
            case "TextContent":
                return f"{var_name}_text"
            case "NumberContent":
                return 0
            case "ImageContent":
                self._imports_needed.add("ImageContent")
                match self.output_format:
                    case ConceptExampleFormat.JSON:
                        return {"_class": "ImageContent", "url": f"{var_name}_url"}
                    case ConceptExampleFormat.PYTHON:
                        return f'ImageContent(url="{var_name}_url")'
            case "PDFContent":
                self._imports_needed.add("PDFContent")
                match self.output_format:
                    case ConceptExampleFormat.JSON:
                        return {"_class": "PDFContent", "url": f"{var_name}_url"}
                    case ConceptExampleFormat.PYTHON:
                        return f'PDFContent(url="{var_name}_url")'
            case _:
                # For other native concepts, generate full content
                structure_class = KajsonManager.get_class_registry().get_class(name=structure_class_name)
                if structure_class and issubclass(structure_class, StuffContent):
                    content = self._generate_content_for_class(structure_class, var_name)
                    return {"content": content}
                return {"content": {}}

    def _handle_native_concept_hard(
        self,
        concept_string: str,
        structure_class_name: str,
    ) -> dict[str, Any]:
        """Handle native concepts in HARD mode - full BaseModel format."""
        structure_class = KajsonManager.get_class_registry().get_class(name=structure_class_name)
        if structure_class and issubclass(structure_class, StuffContent):
            content = self._generate_full_basemodel_content(structure_class)
            return {"concept_code": concept_string, "content": content}
        return {"concept_code": concept_string, "content": {}}

    def _generate_full_basemodel_content(self, content_class: type[StuffContent]) -> Any:
        """Generate full BaseModel content with all fields explicitly shown."""
        class_name = content_class.__name__
        self._imports_needed.add(class_name)

        # Generate all fields from the BaseModel
        fields_dict = self._generate_fields_for_class(content_class)

        match self.output_format:
            case ConceptExampleFormat.JSON:
                return fields_dict
            case ConceptExampleFormat.PYTHON:
                return self._format_class_as_python(class_name, fields_dict)

    def _generate_content_for_class(self, content_class: type[StuffContent], var_name: str) -> Any:
        """Generate example content for a StuffContent class.

        Args:
            content_class: The StuffContent class to generate an example for
            var_name: Variable name for generating contextual example values

        Returns:
            Example content (dict for JSON, class instantiation for Python)
        """
        class_name = content_class.__name__
        self._imports_needed.add(class_name)

        # In LIGHT mode, simple native types have shortcuts
        if self.granularity == ConceptExampleGranularity.LIGHT:
            if class_name == "TextContent":
                return f"{var_name}_text"
            elif class_name == "NumberContent":
                return 0
            elif class_name == "ImageContent":
                match self.output_format:
                    case ConceptExampleFormat.JSON:
                        return {"_class": "ImageContent", "url": f"{var_name}_url"}
                    case ConceptExampleFormat.PYTHON:
                        return f'ImageContent(url="{var_name}_url")'
            elif class_name == "PDFContent":
                match self.output_format:
                    case ConceptExampleFormat.JSON:
                        return {"_class": "PDFContent", "url": f"{var_name}_url"}
                    case ConceptExampleFormat.PYTHON:
                        return f'PDFContent(url="{var_name}_url")'

        # For structured content or HARD mode, generate all fields
        fields_dict = self._generate_fields_for_class(content_class)

        match self.output_format:
            case ConceptExampleFormat.JSON:
                return fields_dict
            case ConceptExampleFormat.PYTHON:
                return self._format_class_as_python(class_name, fields_dict)

    def _format_class_as_python(self, class_name: str, fields: dict[str, Any]) -> str:
        """Format a class instantiation as Python code string."""
        args_parts: list[str] = []
        for field_name, value in fields.items():
            if isinstance(value, str) and not value.startswith('"') and "(" in value:
                # Already formatted as Python code (nested class)
                args_parts.append(f"{field_name}={value}")
            else:
                args_parts.append(f"{field_name}={self._format_python_value(value)}")

        args = ", ".join(args_parts)
        return f"{class_name}({args})"

    def _format_python_value(self, value: Any) -> str:
        """Format a value for Python code representation."""
        if isinstance(value, str):
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

    def _generate_fields_for_class(self, content_class: type[StuffContent]) -> dict[str, Any]:
        """Generate field values for a structured content class."""
        fields_dict: dict[str, Any] = {}

        for field_name, field_info in content_class.model_fields.items():
            field_type = field_info.annotation
            field_value = self._generate_field_value(field_type, field_name)
            fields_dict[field_name] = field_value

        return fields_dict

    def _generate_field_value(self, field_type: Any, field_name: str) -> Any:
        """Generate an example value for a field based on its type."""
        # Unwrap Optional types
        actual_type = self._unwrap_optional(field_type)
        origin = get_origin(actual_type)
        args = get_args(actual_type)

        # Handle list types
        if origin is list:
            return self._generate_list_value(args, field_name)

        # Handle dict types
        if origin is dict:
            return {f"{field_name}_key": f"{field_name}_value"}

        # Handle StrEnum types
        if inspect.isclass(actual_type) and issubclass(actual_type, StrEnum):
            enum_values = list(actual_type)
            return enum_values[0].value if enum_values else f"{field_name}_enum_value"

        # Handle nested StuffContent
        if inspect.isclass(actual_type) and issubclass(actual_type, StuffContent):
            return self._generate_content_for_class(actual_type, field_name)

        # Handle basic types
        return self._generate_basic_value(actual_type, field_name)

    def _unwrap_optional(self, field_type: Any) -> Any:
        """Unwrap Optional[T] to get T."""
        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin is type(None) or (args and type(None) in args):
            # Optional field - get the non-None type
            return next((arg for arg in args if arg is not type(None)), field_type) if args else field_type
        return field_type

    def _generate_list_value(self, args: tuple[Any, ...], field_name: str) -> list[Any]:
        """Generate an example list value."""
        list_item_type = args[0] if args else str

        if not hasattr(list_item_type, "__name__"):
            return []

        item_class_name = list_item_type.__name__

        if item_class_name == "ImageContent":
            self._imports_needed.add("ImageContent")
            match self.output_format:
                case ConceptExampleFormat.JSON:
                    return [{"_class": "ImageContent", "url": f"{field_name}_url_1"}]
                case ConceptExampleFormat.PYTHON:
                    return [f'ImageContent(url="{field_name}_url_1")']

        elif item_class_name == "TextContent":
            if self.granularity == ConceptExampleGranularity.LIGHT:
                return [f"{field_name}_text_1", f"{field_name}_text_2"]
            else:
                # HARD mode - full TextContent
                self._imports_needed.add("TextContent")
                match self.output_format:
                    case ConceptExampleFormat.JSON:
                        return [{"text": f"{field_name}_text_1"}]
                    case ConceptExampleFormat.PYTHON:
                        return [f'TextContent(text="{field_name}_text_1")']

        elif inspect.isclass(list_item_type) and issubclass(list_item_type, StuffContent):
            item_content = self._generate_content_for_class(list_item_type, f"{field_name}_item")
            return [item_content]

        return [f"{field_name}_item_1"]

    def _generate_basic_value(self, actual_type: Any, field_name: str) -> Any:
        """Generate a value for basic Python types."""
        if actual_type is str:
            return f"{field_name}_value"
        elif actual_type is int:
            return 0
        elif actual_type is float:
            return 0.0
        elif actual_type is bool:
            return False
        else:
            # For unknown types, return a placeholder
            type_name = getattr(actual_type, "__name__", str(actual_type))
            return f"{field_name}_value  # TODO: Fill {type_name}"


# Convenience functions


def generate_json_example(
    concept_string: str,
    structure_class_name: str,
    var_name: str,
    granularity: ConceptExampleGranularity = ConceptExampleGranularity.LIGHT,
) -> dict[str, Any] | str | int:
    """Convenience function to generate a JSON format example."""
    generator = ConceptExampleGenerator(ConceptExampleFormat.JSON, granularity)
    return generator.generate_example(concept_string, structure_class_name, var_name)


def generate_python_example(
    concept_string: str,
    structure_class_name: str,
    var_name: str,
    granularity: ConceptExampleGranularity = ConceptExampleGranularity.LIGHT,
) -> tuple[dict[str, Any] | str | int, set[str]]:
    """Convenience function to generate a Python format example.

    Returns:
        Tuple of (example_value, imports_needed)
    """
    generator = ConceptExampleGenerator(ConceptExampleFormat.PYTHON, granularity)
    example = generator.generate_example(concept_string, structure_class_name, var_name)
    return example, generator.imports_needed
