from __future__ import annotations

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from tests.test_pipelines.test_structures_basic import ConceptWithOptionals, ConceptWithSimpleStructure


class ConceptWithDicts(StructuredContent):
    """A structure with dictionary fields."""

    string_dict: dict[str, str] = Field(default_factory=dict, description="A dictionary of strings")
    number_dict: dict[str, int] = Field(default_factory=dict, description="A dictionary of numbers")
    optional_dict: dict[str, str] | None = Field(None, description="An optional dictionary")


class ConceptWithUnions(StructuredContent):
    """A structure with union types."""

    string_or_int: str | int = Field(..., description="A field that can be string or int")
    optional_union: str | bool | None = Field(None, description="An optional union field")
    list_of_unions: list[str | int] = Field(..., description="A list of union types")


class ConceptWithComplexUnions(StructuredContent):
    """A structure with more complex union combinations."""

    mixed_dict: dict[str, str | int | bool] = Field(default_factory=dict, description="A dictionary with mixed value types")
    union_or_list: str | list[int] = Field(..., description="Either a string or a list of integers")
    optional_complex_union: dict[str, str] | list[str] | None = Field(None, description="Optional dict or list")
    number_or_bool: int | float | bool = Field(..., description="Number or boolean value")


class ConceptWithNestedUnions(StructuredContent):
    """A structure with nested unions including other structures."""

    simple_or_complex: ConceptWithSimpleStructure | ConceptWithOptionals = Field(..., description="Simple or complex structure")
    list_of_union_structures: list[ConceptWithSimpleStructure | ConceptWithUnions] = Field(
        default_factory=empty_list_factory_of(ConceptWithSimpleStructure),
        description="List of different structure types",
    )
    optional_nested_union: ConceptWithUnions | ConceptWithComplexUnions | None = Field(
        None,
        description="Optional union of union structures",
    )
