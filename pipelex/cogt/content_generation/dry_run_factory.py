import random
import string
from typing import Any

from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use

from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class DryRunFactory:
    """Factory for creating mock objects during dry runs."""

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
    def make_dry_run_factory(
        cls,
        object_class: type[BaseModelTypeVar],
        snake_case_field_names: set[str] | None = None,
        pascal_case_field_names: set[str] | None = None,
    ) -> type[ModelFactory[BaseModelTypeVar]]:
        """Create a ModelFactory with field-specific providers for dry run mocks.

        Args:
            object_class: The Pydantic model class to create a factory for
            snake_case_field_names: Field names that require snake_case format
            pascal_case_field_names: Field names that require PascalCase format

        Returns:
            A configured ModelFactory class

        """
        # Build class attributes dict with field providers
        class_attrs: dict[str, Any] = {
            "__model__": object_class,
            "__check_model__": True,
            "__use_examples__": True,
            "__allow_none_optionals__": False,
        }

        # Add snake_case providers for specified field names
        if snake_case_field_names:
            for field_name in snake_case_field_names:
                if field_name in object_class.model_fields:
                    class_attrs[field_name] = Use(cls.generate_snake_case_code)

        # Add PascalCase providers for specified field names
        if pascal_case_field_names:
            for field_name in pascal_case_field_names:
                if field_name in object_class.model_fields:
                    class_attrs[field_name] = Use(cls.generate_pascal_case_code)

        # Dynamically create the factory class
        dry_run_factory: type[ModelFactory[BaseModelTypeVar]] = type(  # type: ignore[assignment]
            f"DryRunFactory_{object_class.__name__}",
            (ModelFactory,),
            class_attrs,
        )

        return dry_run_factory
