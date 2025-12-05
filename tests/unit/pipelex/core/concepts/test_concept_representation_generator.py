"""Unit tests for ConceptRepresentationGenerator."""

from pydantic import Field

from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
    generate_json_representation,
    generate_python_representation,
)
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.types import StrEnum

# =============================================================================
# Test Fixtures - Simple classes for unit testing
# =============================================================================


class SimpleContent(StructuredContent):
    """Simple content with basic types."""

    name: str = Field(..., description="A name")
    count: int = Field(..., description="A count")
    rate: float = Field(..., description="A rate")
    active: bool = Field(..., description="Is active")


class StatusEnum(StrEnum):
    """Status enum for testing."""

    PENDING = "pending"
    DONE = "done"


class ContentWithEnum(StructuredContent):
    """Content with an enum field."""

    status: StatusEnum = Field(..., description="Status")


class NestedChild(StructuredContent):
    """A child content class."""

    value: str = Field(..., description="A value")


class ContentWithNestedClass(StructuredContent):
    """Content with a nested StuffContent field."""

    child: NestedChild = Field(..., description="Nested child")


class ContentWithList(StructuredContent):
    """Content with list fields."""

    tags: list[str] = Field(..., description="List of tags")


class ContentWithNestedList(StructuredContent):
    """Content with a list of nested content."""

    children: list[NestedChild] = Field(..., description="List of children")


class ContentWithDict(StructuredContent):
    """Content with a dict field."""

    metadata: dict[str, str] = Field(..., description="Metadata dict")


class ContentWithOptional(StructuredContent):
    """Content with an optional field."""

    maybe_name: str | None = Field(None, description="Optional name")


# =============================================================================
# Tests for ConceptRepresentationFormat enum
# =============================================================================


class TestConceptRepresentationFormat:
    """Test the ConceptRepresentationFormat enum."""

    def test_enum_values(self) -> None:
        """Test that the enum has the expected values."""
        assert ConceptRepresentationFormat.JSON.value == "json"
        assert ConceptRepresentationFormat.PYTHON.value == "python"

    def test_enum_iteration(self) -> None:
        """Test that we can iterate over enum values."""
        values = list(ConceptRepresentationFormat)
        assert len(values) == 2


# =============================================================================
# Tests for generate_field_value - basic types
# =============================================================================


class TestGenerateFieldValueBasicTypes:
    """Test generate_field_value for basic Python types."""

    def test_string_field(self) -> None:
        """String field generates 'fieldname_value'."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(str, "my_field")
        assert result == "my_field_value"

    def test_int_field(self) -> None:
        """Int field generates 0."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(int, "count")
        assert result == 0

    def test_float_field(self) -> None:
        """Float field generates 0.0."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(float, "rate")
        assert result == 0.0

    def test_bool_field(self) -> None:
        """Bool field generates False."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(bool, "active")
        assert result is False


# =============================================================================
# Tests for generate_field_value - complex types
# =============================================================================


class TestGenerateFieldValueComplexTypes:
    """Test generate_field_value for complex types (enums, lists, dicts, nested)."""

    def test_enum_field(self) -> None:
        """Enum field generates first enum value."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(StatusEnum, "status")
        assert result == "pending"

    def test_list_of_strings(self) -> None:
        """List[str] generates list with one placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(list[str], "tags")
        assert result == ["tags_item_value"]

    def test_list_of_nested_content_json(self) -> None:
        """List[StuffContent] generates list with nested dict (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(list[NestedChild], "children")
        expected = [{"value": "value_value"}]
        assert result == expected

    def test_list_of_nested_content_python(self) -> None:
        """List[StuffContent] generates list with instantiation (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_field_value(list[NestedChild], "children")
        expected = ['NestedChild(value="value_value")']
        assert result == expected

    def test_dict_field(self) -> None:
        """Dict field generates placeholder dict."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(dict[str, str], "metadata")
        expected = {"metadata_key": "metadata_value"}
        assert result == expected

    def test_nested_content_json(self) -> None:
        """Nested StuffContent generates dict (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(NestedChild, "child")
        expected = {"value": "value_value"}
        assert result == expected

    def test_nested_content_python(self) -> None:
        """Nested StuffContent generates instantiation (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_field_value(NestedChild, "child")
        expected = 'NestedChild(value="value_value")'
        assert result == expected

    def test_optional_field_unwrapped(self) -> None:
        """Optional[str] is unwrapped and handled as str."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(str | None, "name")
        assert result == "name_value"


# =============================================================================
# Tests for generate_class_representation - JSON format
# =============================================================================


class TestGenerateClassRepresentationJson:
    """Test generate_class_representation with JSON output."""

    def test_simple_content(self) -> None:
        """SimpleContent generates correct JSON dict."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(SimpleContent)
        expected = {
            "name": "name_value",
            "count": 0,
            "rate": 0.0,
            "active": False,
        }
        assert result == expected

    def test_content_with_enum(self) -> None:
        """ContentWithEnum generates correct JSON."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithEnum)
        expected = {"status": "pending"}
        assert result == expected

    def test_content_with_nested_class(self) -> None:
        """ContentWithNestedClass generates nested dict."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithNestedClass)
        expected = {"child": {"value": "value_value"}}
        assert result == expected

    def test_content_with_list(self) -> None:
        """ContentWithList generates list field."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithList)
        expected = {"tags": ["tags_item_value"]}
        assert result == expected

    def test_content_with_nested_list(self) -> None:
        """ContentWithNestedList generates list of nested dicts."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithNestedList)
        expected = {"children": [{"value": "value_value"}]}
        assert result == expected

    def test_content_with_dict(self) -> None:
        """ContentWithDict generates dict field."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithDict)
        expected = {"metadata": {"metadata_key": "metadata_value"}}
        assert result == expected

    def test_content_with_optional(self) -> None:
        """ContentWithOptional handles optional field."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithOptional)
        expected = {"maybe_name": "maybe_name_value"}
        assert result == expected


# =============================================================================
# Tests for generate_class_representation - Python format
# =============================================================================


class TestGenerateClassRepresentationPython:
    """Test generate_class_representation with Python output."""

    def test_simple_content(self) -> None:
        """SimpleContent generates correct Python instantiation."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(SimpleContent)
        expected = 'SimpleContent(name="name_value", count=0, rate=0.0, active=False)'
        assert result == expected

    def test_content_with_nested_class(self) -> None:
        """ContentWithNestedClass generates nested instantiation."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(ContentWithNestedClass)
        expected = 'ContentWithNestedClass(child=NestedChild(value="value_value"))'
        assert result == expected

    def test_content_with_nested_list(self) -> None:
        """ContentWithNestedList generates list of instantiations."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(ContentWithNestedList)
        expected = 'ContentWithNestedList(children=[NestedChild(value="value_value")])'
        assert result == expected


# =============================================================================
# Tests for generate_representation (main entry point)
# =============================================================================


class TestGenerateRepresentation:
    """Test the main generate_representation method."""

    def test_wraps_with_concept_json(self) -> None:
        """Result is wrapped with concept (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.SimpleContent", SimpleContent)
        expected = {
            "concept": "test.SimpleContent",
            "content": {
                "name": "name_value",
                "count": 0,
                "rate": 0.0,
                "active": False,
            },
        }
        assert result == expected

    def test_wraps_with_concept_python(self) -> None:
        """Result is wrapped with concept (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_representation("test.SimpleContent", SimpleContent)
        expected = {
            "concept": "test.SimpleContent",
            "content": 'SimpleContent(name="name_value", count=0, rate=0.0, active=False)',
        }
        assert result == expected

    def test_nested_structure_wrapped(self) -> None:
        """Nested structure is wrapped correctly."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Nested", ContentWithNestedClass)
        expected = {
            "concept": "test.Nested",
            "content": {"child": {"value": "value_value"}},
        }
        assert result == expected


# =============================================================================
# Tests for imports tracking
# =============================================================================


class TestImportsTracking:
    """Test that imports_needed tracks used classes."""

    def test_tracks_main_class(self) -> None:
        """Tracks the main class."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Simple", SimpleContent)
        assert "SimpleContent" in generator.imports_needed

    def test_tracks_nested_classes(self) -> None:
        """Tracks nested classes."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Nested", ContentWithNestedClass)
        assert "ContentWithNestedClass" in generator.imports_needed
        assert "NestedChild" in generator.imports_needed

    def test_clears_on_new_generation(self) -> None:
        """Clears imports on new generation call."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Nested", ContentWithNestedClass)
        generator.generate_representation("test.Simple", SimpleContent)
        assert "NestedChild" not in generator.imports_needed
        assert "SimpleContent" in generator.imports_needed


# =============================================================================
# Tests for convenience functions
# =============================================================================


class TestConvenienceFunctions:
    """Test the convenience functions."""

    def test_generate_json_representation(self) -> None:
        """generate_json_representation returns correct result."""
        result = generate_json_representation("test.Simple", SimpleContent)
        expected = {
            "concept": "test.Simple",
            "content": {
                "name": "name_value",
                "count": 0,
                "rate": 0.0,
                "active": False,
            },
        }
        assert result == expected

    def test_generate_python_representation(self) -> None:
        """generate_python_representation returns correct result and imports."""
        result, imports = generate_python_representation("test.Simple", SimpleContent)
        expected = {
            "concept": "test.Simple",
            "content": 'SimpleContent(name="name_value", count=0, rate=0.0, active=False)',
        }
        assert result == expected
        assert "SimpleContent" in imports
