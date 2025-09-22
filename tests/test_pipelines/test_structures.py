"""Test structures for test_structures domain concepts."""

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent


class ConceptWithSimpleStructure(StructuredContent):
    """A simple structure with basic fields."""

    name: str = Field(..., description="The name field")
    age: int = Field(..., description="The age field")
    is_active: bool = Field(True, description="Whether the item is active")


class ConceptWithOptionals(StructuredContent):
    """A structure with optional fields."""

    required_field: str = Field(..., description="A required field")
    optional_string: Optional[str] = Field(None, description="An optional string field")
    optional_number: Optional[int] = Field(None, description="An optional number field")
    optional_date: Optional[datetime] = Field(None, description="An optional date field")


class ConceptWithLists(StructuredContent):
    """A structure with list fields."""

    string_list: List[str] = Field(default_factory=list, description="A list of strings")
    number_list: List[int] = Field(default_factory=list, description="A list of numbers")
    optional_list: Optional[List[str]] = Field(None, description="An optional list")


class CocneptWithDicts(StructuredContent):
    """A structure with dictionary fields."""

    string_dict: Dict[str, str] = Field(default_factory=dict, description="A dictionary of strings")
    mixed_dict: Dict[str, Union[str, int]] = Field(default_factory=dict, description="A dictionary with mixed values")
    optional_dict: Optional[Dict[str, str]] = Field(None, description="An optional dictionary")


class ConceptWithUnions(StructuredContent):
    """A structure with union types."""

    string_or_int: Union[str, int] = Field(..., description="A field that can be string or int")
    optional_union: Optional[Union[str, bool]] = Field(None, description="An optional union field")
    list_of_unions: List[Union[str, int]] = Field(default_factory=list, description="A list of union types")


class ConceptWithNestedStructures(StructuredContent):
    """A structure with nested structures."""

    simple_nested: ConceptWithSimpleStructure = Field(..., description="A nested simple structure")
    optional_nested: Optional[ConceptWithOptionals] = Field(None, description="An optional nested structure")
    list_of_nested: List[ConceptWithSimpleStructure] = Field(default_factory=list, description="A list of nested structures")
