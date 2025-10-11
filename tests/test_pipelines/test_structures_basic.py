"""Test structures for basic concepts without union types."""

from datetime import datetime

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class ConceptWithSimpleStructure(StructuredContent):
    """A simple structure with basic fields."""

    name: str = Field(..., description="The name field")
    age: int = Field(..., description="The age field")
    is_active: bool = Field(True, description="Whether the item is active")


class ConceptWithOptionals(StructuredContent):
    """A structure with optional fields."""

    required_field: str = Field(..., description="A required field")
    optional_string: str | None = Field(None, description="An optional string field")
    optional_number: int | None = Field(None, description="An optional number field")
    optional_date: datetime | None = Field(None, description="An optional date field")


class ConceptWithLists(StructuredContent):
    """A structure with list fields."""

    string_list: list[str] = Field(default_factory=list, description="A list of strings")
    number_list: list[int] = Field(default_factory=empty_list_factory_of(int), description="A list of numbers")
    optional_list: list[str] | None = Field(None, description="An optional list")


class ConceptWithNestedStructures(StructuredContent):
    """A structure with nested structures."""

    simple_nested: ConceptWithSimpleStructure = Field(..., description="A nested simple structure")
    optional_nested: ConceptWithOptionals | None = Field(None, description="An optional nested structure")
    list_of_nested: list[ConceptWithSimpleStructure] = Field(
        default_factory=empty_list_factory_of(ConceptWithSimpleStructure), description="A list of nested structures"
    )
