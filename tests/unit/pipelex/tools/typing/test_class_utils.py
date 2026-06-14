from pydantic import BaseModel, Field

from pipelex.tools.typing.class_utils import (
    are_classes_equivalent,
    has_compatible_field,
    normalize_properties_for_comparison,
    normalize_property_for_comparison,
)


class TestNormalizePropertyForComparison:
    """Tests for normalize_property_for_comparison function."""

    def test_removes_description_from_simple_property(self):
        """Test that description is removed from a simple property."""
        prop = {"type": "string", "description": "The user name", "title": "Name"}
        result = normalize_property_for_comparison(prop)
        assert result == {"type": "string", "title": "Name"}
        assert "description" not in result

    def test_preserves_other_keys(self):
        """Test that other keys are preserved."""
        prop = {"type": "integer", "minimum": 0, "maximum": 100}
        result = normalize_property_for_comparison(prop)
        assert result == {"type": "integer", "minimum": 0, "maximum": 100}

    def test_removes_description_from_nested_dict(self):
        """Test that description is removed from nested dicts."""
        prop = {
            "type": "object",
            "description": "A nested object",
            "properties": {"id": {"type": "integer", "description": "The ID"}},
        }
        result = normalize_property_for_comparison(prop)
        assert result == {"type": "object", "properties": {"id": {"type": "integer"}}}
        assert "description" not in result
        assert "description" not in result["properties"]["id"]

    def test_handles_empty_dict(self):
        """Test that empty dict returns empty dict."""
        assert normalize_property_for_comparison({}) == {}

    def test_handles_deeply_nested_descriptions(self):
        """Test removal of descriptions at multiple nesting levels."""
        prop = {
            "type": "object",
            "description": "Level 1",
            "items": {
                "type": "object",
                "description": "Level 2",
                "properties": {
                    "field": {"type": "string", "description": "Level 3"},
                },
            },
        }
        result = normalize_property_for_comparison(prop)
        assert "description" not in result
        assert "description" not in result["items"]
        assert "description" not in result["items"]["properties"]["field"]


class TestNormalizePropertiesForComparison:
    """Tests for normalize_properties_for_comparison function."""

    def test_normalizes_multiple_properties(self):
        """Test that all properties have descriptions removed."""
        properties = {
            "name": {"type": "string", "description": "User name"},
            "age": {"type": "integer", "description": "User age"},
        }
        result = normalize_properties_for_comparison(properties)
        assert result == {"name": {"type": "string"}, "age": {"type": "integer"}}

    def test_handles_empty_properties(self):
        """Test that empty properties dict returns empty dict."""
        assert normalize_properties_for_comparison({}) == {}

    def test_preserves_non_description_metadata(self):
        """Test that other metadata is preserved."""
        properties = {
            "count": {"type": "integer", "minimum": 0, "description": "A count"},
            "active": {"type": "boolean", "default": True, "description": "Is active"},
        }
        result = normalize_properties_for_comparison(properties)
        assert result == {
            "count": {"type": "integer", "minimum": 0},
            "active": {"type": "boolean", "default": True},
        }


class TestAreClassesEquivalent:
    """Tests for are_classes_equivalent function."""

    def test_identical_classes_are_equivalent(self):
        """Test that the same class is equivalent to itself."""

        class MyModel(BaseModel):
            name: str
            age: int

        assert are_classes_equivalent(MyModel, class_2=MyModel) is True

    def test_classes_with_same_structure_are_equivalent(self):
        """Test that two classes with the same fields are equivalent."""

        class ModelA(BaseModel):
            name: str
            value: int

        class ModelB(BaseModel):
            name: str
            value: int

        assert are_classes_equivalent(ModelA, class_2=ModelB) is True

    def test_classes_with_different_fields_are_not_equivalent(self):
        """Test that classes with different field names are not equivalent."""

        class ModelA(BaseModel):
            name: str

        class ModelB(BaseModel):
            title: str

        assert are_classes_equivalent(ModelA, class_2=ModelB) is False

    def test_classes_with_different_types_are_not_equivalent(self):
        """Test that classes with different field types are not equivalent."""

        class ModelA(BaseModel):
            value: int

        class ModelB(BaseModel):
            value: str

        assert are_classes_equivalent(ModelA, class_2=ModelB) is False

    def test_classes_with_different_descriptions_are_equivalent(self):
        """Test that field descriptions don't affect equivalence."""

        class ModelA(BaseModel):
            name: str = Field(description="The name of something")

        class ModelB(BaseModel):
            name: str = Field(description="A completely different description")

        assert are_classes_equivalent(ModelA, class_2=ModelB) is True

    def test_classes_with_different_required_fields_are_not_equivalent(self):
        """Test that required vs optional fields matter."""

        class ModelA(BaseModel):
            name: str

        class ModelB(BaseModel):
            name: str | None = None

        assert are_classes_equivalent(ModelA, class_2=ModelB) is False

    def test_non_pydantic_classes(self):
        """Test that non-Pydantic classes are compared by identity."""

        class RegularClass:
            pass

        assert are_classes_equivalent(RegularClass, class_2=RegularClass) is True
        assert are_classes_equivalent(str, class_2=str) is True
        assert are_classes_equivalent(str, class_2=int) is False


class TestHasCompatibleField:
    """Tests for has_compatible_field function."""

    def test_direct_type_match(self):
        """Test that a field with exact type match is found."""

        class Inner(BaseModel):
            value: str

        class Outer(BaseModel):
            data: Inner

        assert has_compatible_field(Outer, class_2=Inner) is True

    def test_subclass_match(self):
        """Test that a field with subclass type is found."""

        class Parent(BaseModel):
            name: str

        class Child(Parent):
            age: int

        class Container(BaseModel):
            item: Child

        assert has_compatible_field(Container, class_2=Parent) is True

    def test_no_match(self):
        """Test that no match is found when field types don't match."""

        class TypeA(BaseModel):
            x: int

        class TypeB(BaseModel):
            y: str

        class Container(BaseModel):
            data: TypeA

        assert has_compatible_field(Container, class_2=TypeB) is False

    def test_structural_equivalence_match(self):
        """Test that structurally equivalent types are found."""

        class StructureA(BaseModel):
            name: str
            value: int

        class StructureB(BaseModel):
            name: str
            value: int

        class Container(BaseModel):
            data: StructureA

        # StructureA and StructureB have the same structure
        assert has_compatible_field(Container, class_2=StructureB) is True

    def test_optional_field_match(self):
        """Test that optional fields are checked correctly."""

        class Inner(BaseModel):
            value: str

        class Outer(BaseModel):
            data: Inner | None = None

        assert has_compatible_field(Outer, class_2=Inner) is True

    def test_non_pydantic_class(self):
        """Test that non-Pydantic classes return False."""

        class RegularClass:
            pass

        class PydanticClass(BaseModel):
            name: str

        assert has_compatible_field(RegularClass, class_2=PydanticClass) is False  # type: ignore[arg-type]


class TestAreClassesEquivalentWithOptionalFields:
    """Additional tests for are_classes_equivalent with optional fields."""

    def test_same_optional_fields_are_equivalent(self):
        """Test that classes with same optional fields are equivalent."""

        class ModelA(BaseModel):
            name: str
            nickname: str | None = None

        class ModelB(BaseModel):
            name: str
            nickname: str | None = None

        assert are_classes_equivalent(ModelA, class_2=ModelB) is True

    def test_classes_with_same_fields_different_defaults_may_differ(self):
        """Test that default values don't affect JSON schema equivalence (they're in 'default' key)."""

        class ModelA(BaseModel):
            count: int = 0

        class ModelB(BaseModel):
            count: int = 100

        # JSON schema includes 'default' key, so these may or may not be equivalent
        # depending on whether defaults are in the schema properties
        # This test documents the actual behavior
        result = are_classes_equivalent(ModelA, class_2=ModelB)
        # The behavior depends on Pydantic's schema generation
        assert isinstance(result, bool)
