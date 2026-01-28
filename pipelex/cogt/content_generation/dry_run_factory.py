import random
import string
from typing import Any

from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Ignore, Use
from pydantic.fields import FieldInfo

from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.types import StrEnum


class MockFormat(StrEnum):
    """Mock format specifications for Field json_schema_extra."""

    SNAKE_CASE = "snake_case"
    PASCAL_CASE = "pascal_case"
    IGNORE = "ignore"


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
    def _detect_format_constraints(cls, object_class: type[BaseModelTypeVar]) -> tuple[set[str], set[str], set[str]]:
        """Detect format constraints from model field definitions.

        Scans all fields for json_schema_extra containing mock_format.

        Args:
            object_class: The Pydantic model class to scan

        Returns:
            Tuple of (snake_case_fields, pascal_case_fields, ignored_fields)
        """
        snake_case_fields: set[str] = set()
        pascal_case_fields: set[str] = set()
        ignored_fields: set[str] = set()

        for field_name, field_info in object_class.model_fields.items():
            mock_format = cls._get_mock_format_from_field(field_info)

            match mock_format:
                case MockFormat.SNAKE_CASE:
                    snake_case_fields.add(field_name)
                case MockFormat.PASCAL_CASE:
                    pascal_case_fields.add(field_name)
                case MockFormat.IGNORE:
                    ignored_fields.add(field_name)
                case None:
                    pass

        return snake_case_fields, pascal_case_fields, ignored_fields

    @classmethod
    def make_dry_run_factory(
        cls,
        object_class: type[BaseModelTypeVar],
        snake_case_field_names: set[str] | None = None,
        pascal_case_field_names: set[str] | None = None,
    ) -> type[ModelFactory[BaseModelTypeVar]]:
        """Create a ModelFactory with field-specific providers for dry run mocks.

        Automatically detects format constraints from Field definitions using
        json_schema_extra={"mock_format": "snake_case"|"pascal_case"|"ignore"}.
        Explicit field name sets take precedence over auto-detected constraints.

        Args:
            object_class: The Pydantic model class to create a factory for
            snake_case_field_names: Field names that require snake_case format (overrides auto-detection)
            pascal_case_field_names: Field names that require PascalCase format (overrides auto-detection)

        Returns:
            A configured ModelFactory class
        """
        # Auto-detect format constraints from field definitions
        detected_snake, detected_pascal, detected_ignored = cls._detect_format_constraints(object_class)

        # Merge explicit field names with auto-detected ones (explicit takes precedence)
        all_snake_case = detected_snake | (snake_case_field_names or set())
        all_pascal_case = detected_pascal | (pascal_case_field_names or set())

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

        # Add Ignore for fields that should be None/default
        for field_name in detected_ignored:
            if field_name in object_class.model_fields:
                class_attrs[field_name] = Ignore()

        # Dynamically create the factory class
        dry_run_factory: type[ModelFactory[BaseModelTypeVar]] = type(  # type: ignore[assignment]
            f"DryRunFactory_{object_class.__name__}",
            (ModelFactory,),
            class_attrs,
        )

        return dry_run_factory
