import random
import string
import types
import typing
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Union, get_args, get_origin

from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Ignore, PostGenerated, Use
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class MockFormat(StrEnum):
    """Mock format specifications for Field json_schema_extra."""

    SNAKE_CASE = "snake_case"
    PASCAL_CASE = "pascal_case"
    CONCEPT_REF = "concept_ref"
    IGNORE = "ignore"
    DICT_SNAKE_KEY_PASCAL_VALUE = "dict_snake_key_pascal_value"
    DICT_SINGLE_EXTRACT_INPUT = "dict_single_extract_input"


class DryRunFactory:
    """Factory for creating mock objects during dry runs.

    Automatically detects format constraints from Pydantic Field definitions using
    the `mock_format` key in `json_schema_extra`. Supported formats:
    - "snake_case": Generates values like "mock_abcd"
    - "pascal_case": Generates values like "MockAbcd"

    Example Field definition:
        domain_code: str = Field(
            description="Domain code",
            json_schema_extra={"mock_format": "snake_case"}
        )
    """

    @classmethod
    def generate_snake_case_code(cls) -> str:
        """Generate a valid snake_case code for dry run mocks."""
        suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        return f"mock_{suffix}"

    @classmethod
    def generate_pascal_case_code(cls) -> str:
        """Generate a valid PascalCase code for dry run mocks."""
        suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        return f"Mock{suffix.capitalize()}"

    @classmethod
    def generate_concept_ref(cls) -> str:
        """Generate a valid concept reference for dry run mocks.

        Format: snake_case.PascalCase (e.g., mock_domain.MockConcept)
        """
        return f"{cls.generate_snake_case_code()}.{cls.generate_pascal_case_code()}"

    @classmethod
    def generate_dict_snake_key_pascal_value(cls, *, num_items: int = 2) -> dict[str, str]:
        """Generate a dict with snake_case keys and PascalCase values."""
        result: dict[str, str] = {}
        for _ in range(num_items):
            key = cls.generate_snake_case_code()
            value = cls.generate_pascal_case_code()
            result[key] = value
        return result

    @staticmethod
    def _main_pipe_from_pipe_dict(  # kw-only: ignore -- polyfactory PostGenerated invokes it positionally
        _field_name: str,
        values: dict[str, Any],
    ) -> str:
        """PostGenerated callback that picks a key from the pipe dict for main_pipe."""
        pipe_dict: dict[str, Any] | None = values.get("pipe")
        if pipe_dict and len(pipe_dict) > 0:
            pipe_keys: list[str] = list(pipe_dict.keys())
            return random.choice(pipe_keys)
        # Fallback to a mock value if pipe dict is empty/not available
        return "mock_" + "".join(random.choices(string.ascii_lowercase, k=4))

    @classmethod
    def generate_dict_single_extract_input(cls) -> dict[str, str]:
        """Generate a dict with a single entry for PipeExtract inputs.

        The key is snake_case and the value is either 'Image' or 'Document'.
        """
        key = cls.generate_snake_case_code()
        value = random.choice(["Image", "Document"])
        return {key: value}

    @classmethod
    def _get_examples_from_field(cls, field_info: FieldInfo) -> list[Any] | None:
        """Extract examples from a field's definition.

        Returns the examples list if present, None otherwise.
        """
        if hasattr(field_info, "examples") and field_info.examples:
            return list(field_info.examples)
        return None

    @classmethod
    def _get_mock_format_from_field(cls, field_info: FieldInfo) -> MockFormat | None:
        """Extract mock_format from a field's json_schema_extra.

        Args:
            field_info: The Pydantic FieldInfo object

        Returns:
            The MockFormat enum value if specified and valid, None otherwise
        """
        extra = field_info.json_schema_extra
        if extra is None:
            return None

        if isinstance(extra, dict):
            mock_format: Any = extra.get("mock_format")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(mock_format, MockFormat):
                return mock_format
            if isinstance(mock_format, str):
                try:
                    return MockFormat(mock_format)
                except ValueError:
                    return None

        return None

    @classmethod
    def _detect_examples_constraints(cls, object_class: type[BaseModelTypeVar]) -> dict[str, list[Any]]:
        """Detect fields with examples and return mapping of field_name -> examples list."""
        result: dict[str, list[Any]] = {}
        for field_name, field_info in object_class.model_fields.items():
            examples = cls._get_examples_from_field(field_info)
            if examples:
                result[field_name] = examples
        return result

    @classmethod
    def _get_literal_values_from_annotation(cls, annotation: Any) -> tuple[Any, ...] | None:
        """Extract Literal values from a type annotation, handling Optional wrapping.

        Args:
            annotation: The type annotation to inspect

        Returns:
            Tuple of literal values if the annotation is a Literal type, None otherwise
        """
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Direct Literal type: Literal["a", "b", "c"]
        if origin is typing.Literal:
            return args

        # Optional[Literal[...]] or Literal[...] | None: unwrap and check inner type
        if origin is Union or origin is types.UnionType:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return cls._get_literal_values_from_annotation(non_none_args[0])

        return None

    @classmethod
    def _detect_literal_fields(cls, object_class: type[BaseModel]) -> dict[str, tuple[Any, ...]]:
        """Detect fields with Literal type annotations and return their valid values.

        Args:
            object_class: The Pydantic model class to scan

        Returns:
            Dict mapping field names to their tuple of valid Literal values
        """
        result: dict[str, tuple[Any, ...]] = {}
        for field_name, field_info in object_class.model_fields.items():
            annotation = field_info.annotation
            if annotation is None:
                continue
            literal_values = cls._get_literal_values_from_annotation(annotation)
            if literal_values:
                result[field_name] = literal_values
        return result

    @staticmethod
    def _make_example_picker(examples: list[Any]) -> Callable[[], Any]:
        """Create a closure that picks a random example from the list."""

        def picker() -> Any:
            return random.choice(examples)

        return picker

    @classmethod
    def _find_nested_base_model_classes(
        cls,
        object_class: type[BaseModel],
        *,
        visited: set[type[BaseModel]] | None = None,
    ) -> set[type[BaseModel]]:
        """Recursively find all nested BaseModel classes in a model's field annotations.

        Args:
            object_class: The Pydantic model class to scan
            visited: Set of already visited classes to avoid infinite recursion

        Returns:
            Set of all nested BaseModel classes found
        """
        if visited is None:
            visited = set()

        if object_class in visited:
            return set()

        visited.add(object_class)
        nested_classes: set[type[BaseModel]] = set()

        for field_info in object_class.model_fields.values():
            annotation = field_info.annotation
            if annotation is None:
                continue

            # Extract types from complex annotations (Union, List, Dict, etc.)
            types_to_check = cls._extract_types_from_annotation(annotation)

            for type_to_check in types_to_check:
                if isinstance(type_to_check, type) and issubclass(type_to_check, BaseModel) and type_to_check not in visited:
                    nested_classes.add(type_to_check)
                    # Recursively find nested classes
                    nested_classes.update(cls._find_nested_base_model_classes(type_to_check, visited=visited))

        return nested_classes

    @classmethod
    def _extract_types_from_annotation(cls, annotation: Any) -> list[Any]:
        """Extract all concrete types from a type annotation.

        Handles Union, List, Dict, and other generic types.
        """
        result: list[Any] = []
        origin = get_origin(annotation)

        if origin is None:
            # Simple type, not a generic
            result.append(annotation)
        else:
            # Generic type, extract args
            args = get_args(annotation)
            for arg in args:
                result.extend(cls._extract_types_from_annotation(arg))

        return result

    @classmethod
    def _create_nested_factory(
        cls,
        nested_class: type[BaseModel],
    ) -> type[ModelFactory[Any]]:
        """Create a factory for a nested BaseModel class with examples enabled."""
        # Build class attributes for the nested factory
        class_attrs: dict[str, Any] = {
            "__model__": nested_class,
            "__use_examples__": True,
            "__allow_none_optionals__": False,
        }

        # Detect fields with examples and create providers
        fields_with_examples = cls._detect_examples_constraints(nested_class)  # type: ignore[arg-type]
        for field_name, examples in fields_with_examples.items():
            if field_name in nested_class.model_fields:
                class_attrs[field_name] = Use(cls._make_example_picker(examples))

        # Detect format constraints
        detected_formats = cls._detect_format_constraints(nested_class)  # type: ignore[arg-type]

        for field_name in detected_formats[MockFormat.SNAKE_CASE]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls.generate_snake_case_code)

        for field_name in detected_formats[MockFormat.PASCAL_CASE]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls.generate_pascal_case_code)

        for field_name in detected_formats[MockFormat.CONCEPT_REF]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls.generate_concept_ref)

        for field_name in detected_formats[MockFormat.IGNORE]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Ignore()

        for field_name in detected_formats[MockFormat.DICT_SNAKE_KEY_PASCAL_VALUE]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls.generate_dict_snake_key_pascal_value)

        for field_name in detected_formats[MockFormat.DICT_SINGLE_EXTRACT_INPUT]:
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls.generate_dict_single_extract_input)

        # Add Literal type providers (fields with choices)
        literal_fields = cls._detect_literal_fields(nested_class)
        for field_name, literal_values in literal_fields.items():
            if field_name in nested_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls._make_example_picker(list(literal_values)))

        # Create the factory class using ModelFactory directly
        factory: type[ModelFactory[Any]] = type(
            f"DryRunFactory_{nested_class.__name__}",
            (ModelFactory,),
            class_attrs,
        )
        return factory

    @classmethod
    def _detect_format_constraints(cls, object_class: type[BaseModelTypeVar]) -> dict[MockFormat, set[str]]:
        """Detect format constraints from model field definitions.

        Scans all fields for json_schema_extra containing mock_format.

        Args:
            object_class: The Pydantic model class to scan

        Returns:
            Dict mapping MockFormat values to sets of field names
        """
        result: dict[MockFormat, set[str]] = {mock_format: set() for mock_format in MockFormat}

        for field_name, field_info in object_class.model_fields.items():
            mock_format = cls._get_mock_format_from_field(field_info)
            if mock_format is not None:
                result[mock_format].add(field_name)

        return result

    @classmethod
    def make_dry_run_factory(
        cls,
        object_class: type[BaseModelTypeVar],
        *,
        snake_case_field_names: set[str] | None = None,
        pascal_case_field_names: set[str] | None = None,
    ) -> type[ModelFactory[BaseModelTypeVar]]:
        """Create a ModelFactory with field-specific providers for dry run mocks.

        Automatically detects format constraints from Field definitions using
        json_schema_extra={"mock_format": "snake_case"|"pascal_case"|"ignore"|...}.
        Explicit field name sets take precedence over auto-detected constraints.

        Args:
            object_class: The Pydantic model class to create a factory for
            snake_case_field_names: Field names that require snake_case format (overrides auto-detection)
            pascal_case_field_names: Field names that require PascalCase format (overrides auto-detection)

        Returns:
            A configured ModelFactory class
        """
        # Auto-detect format constraints from field definitions
        detected_formats = cls._detect_format_constraints(object_class)

        # Merge explicit field names with auto-detected ones (explicit takes precedence)
        detected_snake_case: set[str] = detected_formats[MockFormat.SNAKE_CASE]
        detected_pascal_case: set[str] = detected_formats[MockFormat.PASCAL_CASE]
        all_snake_case = detected_snake_case | (snake_case_field_names or set())
        all_pascal_case = detected_pascal_case | (pascal_case_field_names or set())

        # Build class attributes dict with field providers
        class_attrs: dict[str, Any] = {
            "__model__": object_class,
            "__check_model__": True,
            "__use_examples__": True,
            "__allow_none_optionals__": False,
        }

        # Add snake_case providers
        for field_name in all_snake_case:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Use(cls.generate_snake_case_code)

        # Add PascalCase providers
        for field_name in all_pascal_case:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Use(cls.generate_pascal_case_code)

        # Add concept ref providers (snake_case@PascalCase)
        for field_name in detected_formats[MockFormat.CONCEPT_REF]:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Use(cls.generate_concept_ref)

        # Add Ignore for fields that should be None/default
        for field_name in detected_formats[MockFormat.IGNORE]:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Ignore()

        # Add dict with snake_case keys and PascalCase values providers
        for field_name in detected_formats[MockFormat.DICT_SNAKE_KEY_PASCAL_VALUE]:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Use(cls.generate_dict_snake_key_pascal_value)

        # Add single extract input dict providers
        for field_name in detected_formats[MockFormat.DICT_SINGLE_EXTRACT_INPUT]:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Use(cls.generate_dict_single_extract_input)

        # Detect fields with examples and create providers that pick from them
        fields_with_examples = cls._detect_examples_constraints(object_class)
        for field_name, examples in fields_with_examples.items():
            if field_name in object_class.model_fields and field_name not in class_attrs:
                # Create a closure to capture the specific examples list
                class_attrs[field_name] = Use(cls._make_example_picker(examples))

        # Add Literal type providers (fields with choices like Literal["a", "b", "c"])
        literal_fields = cls._detect_literal_fields(object_class)
        for field_name, literal_values in literal_fields.items():
            if field_name in object_class.model_fields and field_name not in class_attrs:
                class_attrs[field_name] = Use(cls._make_example_picker(list(literal_values)))

        # Add cross-field dependencies using PostGenerated
        # For models with main_pipe that must reference a key in pipe dict
        if "main_pipe" in object_class.model_fields and "pipe" in object_class.model_fields:
            class_attrs["main_pipe"] = PostGenerated(cls._main_pipe_from_pipe_dict)

        # Find all nested BaseModel classes and create factories for them
        nested_classes = cls._find_nested_base_model_classes(object_class)  # type: ignore[arg-type]
        nested_factories: dict[type[BaseModel], type[ModelFactory[Any]]] = {}
        for nested_class in nested_classes:
            nested_factory = cls._create_nested_factory(nested_class)
            nested_factories[nested_class] = nested_factory

        # Register nested factories using __base_factory_overrides__ attribute
        # This tells polyfactory to use our custom factories for these model types
        if nested_factories:
            class_attrs["__base_factory_overrides__"] = nested_factories

        # Dynamically create the factory class using ModelFactory as the parent
        dry_run_factory: type[ModelFactory[BaseModelTypeVar]] = type(  # type: ignore[assignment]
            f"DryRunFactory_{object_class.__name__}",
            (ModelFactory,),
            class_attrs,
        )

        return dry_run_factory
