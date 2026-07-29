"""Unit tests for ConceptRepresentationGenerator."""

import datetime
from enum import StrEnum

from pydantic import Field

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
    generate_json_representation,
    generate_python_representation,
)
from pipelex.core.stuffs.structured_content import StructuredContent

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


class ContentWithRequiredAndOptional(StructuredContent):
    """Content with both required and optional fields (like ImageContent)."""

    url: str = Field(..., description="Required URL")
    source_prompt: str | None = Field(None, description="Optional prompt")
    caption: str | None = Field(None, description="Optional caption")
    base_64: str | None = Field(None, description="Optional base64")


# =============================================================================
# Tests for ConceptRepresentationFormat enum
# =============================================================================


class TestConceptRepresentationFormat:
    """Test the ConceptRepresentationFormat enum."""

    def test_enum_values(self) -> None:
        """Test that the enum has the expected values."""
        assert ConceptRepresentationFormat.JSON.value == "json"
        assert ConceptRepresentationFormat.PYTHON.value == "python"
        assert ConceptRepresentationFormat.SCHEMA.value == "schema"

    def test_enum_iteration(self) -> None:
        """Test that we can iterate over enum values."""
        values = list(ConceptRepresentationFormat)
        assert len(values) == 3


# =============================================================================
# Tests for generate_field_value - basic types
# =============================================================================


class TestGenerateFieldValueBasicTypes:
    """Test generate_field_value for basic Python types."""

    def test_string_field(self) -> None:
        """String field generates 'fieldname_value'."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(str, field_name="my_field")
        assert result == "my_field_value"

    def test_int_field(self) -> None:
        """Int field generates 0."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(int, field_name="count")
        assert result == 0

    def test_float_field(self) -> None:
        """Float field generates 0.0."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(float, field_name="rate")
        assert result == 0.0

    def test_bool_field(self) -> None:
        """Bool field generates False."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(bool, field_name="active")
        assert result is False

    def test_int_or_float_union_field(self) -> None:
        """Int | float union field generates a numeric value (1), not a string placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(int | float, field_name="number")
        assert isinstance(result, (int, float)), f"Expected int or float, got {type(result)}: {result}"
        assert result == 1

    def test_date_field_is_valid_iso_date(self) -> None:
        """A datetime.date field generates a real ISO date, not a 'field_date' placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(datetime.date, field_name="issued_on")
        assert isinstance(result, str)
        assert datetime.date.fromisoformat(result) is not None
        # Extended ISO (YYYY-MM-DD), not the compact all-digit form DateContent rejects.
        assert "-" in result, f"Expected extended ISO date (YYYY-MM-DD), got: {result}"

    def test_datetime_field_is_valid_iso_datetime(self) -> None:
        """A datetime.datetime field generates a real ISO datetime, not a placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(datetime.datetime, field_name="recorded_at")
        assert isinstance(result, str)
        assert datetime.datetime.fromisoformat(result) is not None
        # A real datetime carries the time component — a date-only string would also parse here.
        assert "T" in result, f"Expected an ISO datetime with a time component, got: {result}"

    def test_time_field_is_valid_iso_time(self) -> None:
        """A datetime.time field generates a real ISO time, not a placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(datetime.time, field_name="opens_at")
        assert isinstance(result, str)
        assert datetime.time.fromisoformat(result) is not None

    def test_float_or_int_union_field(self) -> None:
        """Float | int union field generates a numeric value (1), not a string placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(float | int, field_name="amount")
        assert isinstance(result, (int, float)), f"Expected int or float, got {type(result)}: {result}"
        assert result == 1


# =============================================================================
# Tests for generate_field_value - complex types
# =============================================================================


class TestGenerateFieldValueComplexTypes:
    """Test generate_field_value for complex types (enums, lists, dicts, nested)."""

    def test_enum_field(self) -> None:
        """Enum field generates first enum value."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(StatusEnum, field_name="status")
        assert result == "pending"

    def test_list_of_strings(self) -> None:
        """List[str] generates list with one placeholder."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(list[str], field_name="tags")
        assert result == ["tags_item_value"]

    def test_list_of_nested_content_json(self) -> None:
        """List[StuffContent] generates list with nested dict (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(list[NestedChild], field_name="children")
        expected = [{"value": "value_value"}]
        assert result == expected

    def test_list_of_nested_content_python(self) -> None:
        """List[StuffContent] generates list with instantiation (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_field_value(list[NestedChild], field_name="children")
        expected = ['NestedChild(value="value_value")']
        assert result == expected

    def test_dict_field(self) -> None:
        """Dict field generates placeholder dict."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(dict[str, str], field_name="metadata")
        expected = {"metadata_key": "metadata_value"}
        assert result == expected

    def test_nested_content_json(self) -> None:
        """Nested StuffContent generates dict (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(NestedChild, field_name="child")
        expected = {"value": "value_value"}
        assert result == expected

    def test_nested_content_python(self) -> None:
        """Nested StuffContent generates instantiation (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_field_value(NestedChild, field_name="child")
        expected = 'NestedChild(value="value_value")'
        assert result == expected

    def test_optional_field_unwrapped(self) -> None:
        """Optional[str] is unwrapped and handled as str."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(str | None, field_name="name")
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
        result = generator.generate_representation("test.SimpleContent", structure_class=SimpleContent)
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
        result = generator.generate_representation("test.SimpleContent", structure_class=SimpleContent)
        expected = {
            "concept": "test.SimpleContent",
            "content": 'SimpleContent(name="name_value", count=0, rate=0.0, active=False)',
        }
        assert result == expected

    def test_nested_structure_wrapped(self) -> None:
        """Nested structure is wrapped correctly."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("test.Nested", structure_class=ContentWithNestedClass)
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
        generator.generate_representation("test.Simple", structure_class=SimpleContent)
        assert "SimpleContent" in generator.imports_needed

    def test_tracks_nested_classes(self) -> None:
        """Tracks nested classes."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Nested", structure_class=ContentWithNestedClass)
        assert "ContentWithNestedClass" in generator.imports_needed
        assert "NestedChild" in generator.imports_needed

    def test_clears_on_new_generation(self) -> None:
        """Clears imports on new generation call."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        generator.generate_representation("test.Nested", structure_class=ContentWithNestedClass)
        generator.generate_representation("test.Simple", structure_class=SimpleContent)
        assert "NestedChild" not in generator.imports_needed
        assert "SimpleContent" in generator.imports_needed


# =============================================================================
# Tests for convenience functions
# =============================================================================


class TestConvenienceFunctions:
    """Test the convenience functions."""

    def test_generate_json_representation(self) -> None:
        """generate_json_representation returns correct result."""
        result = generate_json_representation("test.Simple", structure_class=SimpleContent)
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
        result, imports = generate_python_representation("test.Simple", structure_class=SimpleContent)
        expected = {
            "concept": "test.Simple",
            "content": 'SimpleContent(name="name_value", count=0, rate=0.0, active=False)',
        }
        assert result == expected
        assert "SimpleContent" in imports


# =============================================================================
# Tests for include_optional parameter
# =============================================================================


class TestIncludeOptionalParameter:
    """Test that optional fields can be excluded from generation."""

    def test_excludes_optional_fields_json(self) -> None:
        """With include_optional=False, optional fields are excluded (JSON)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithRequiredAndOptional, include_optional=False)
        assert isinstance(result, dict)
        assert "url" in result
        assert result["url"] == "https://mock.invalid/url"
        # Verify optional fields are NOT present
        assert "source_prompt" not in result
        assert "caption" not in result
        assert "base_64" not in result

    def test_excludes_optional_fields_python(self) -> None:
        """With include_optional=False, optional fields are excluded (Python)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(ContentWithRequiredAndOptional, include_optional=False)
        assert isinstance(result, str)
        assert result.startswith('ContentWithRequiredAndOptional(url="https://mock.invalid/url"')
        assert result.endswith('")')

    def test_includes_optional_fields_by_default(self) -> None:
        """By default, optional fields ARE included (backward compatibility)."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithRequiredAndOptional)
        # All fields should be present by default
        assert "url" in result
        assert "source_prompt" in result
        assert "caption" in result
        assert "base_64" in result

    def test_all_optional_returns_empty_dict_json(self) -> None:
        """Content with only optional fields returns empty dict when include_optional=False."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithOptional, include_optional=False)
        expected: dict[str, str] = {}
        assert result == expected

    def test_all_optional_returns_empty_instantiation_python(self) -> None:
        """Content with only optional fields returns empty instantiation when include_optional=False."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(ContentWithOptional, include_optional=False)
        expected = "ContentWithOptional()"
        assert result == expected

    def test_image_content_only_url_required(self) -> None:
        """ImageContent should only have url when include_optional=False."""
        from pipelex.core.stuffs.image_content import ImageContent  # noqa: PLC0415

        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ImageContent, include_optional=False)
        assert isinstance(result, dict)
        assert "url" in result
        assert result["url"] == "https://mock.invalid/url"
        # Verify optional fields are NOT present
        assert "source_prompt" not in result
        assert "caption" not in result
        assert "base_64" not in result


# =============================================================================
# Tests for SCHEMA format with is_multiple parameter
# =============================================================================


class TestSchemaRepresentationWithMultiple:
    """Test schema representation with is_multiple parameter."""

    def test_schema_single_item(self) -> None:
        """Schema for single item returns the JSON schema directly."""
        concept = Concept(
            code="SimpleContent",
            domain_code="test",
            description="Test concept",
            structure_class_name="SimpleContent",
        )

        result, imports = concept.render_concept_representation(
            structure_class=SimpleContent,
            output_format=ConceptRepresentationFormat.SCHEMA,
            is_multiple=False,
        )

        assert result["concept"] == "test.SimpleContent"
        assert result["content"]["type"] == "object"
        assert "properties" in result["content"]
        assert "name" in result["content"]["properties"]
        assert "count" in result["content"]["properties"]
        assert imports == set()

    def test_schema_multiple_items_wraps_in_array(self) -> None:
        """Schema for multiple items wraps the schema in an array type."""
        concept = Concept(
            code="SimpleContent",
            domain_code="test",
            description="Test concept",
            structure_class_name="SimpleContent",
        )

        result, imports = concept.render_concept_representation(
            structure_class=SimpleContent,
            output_format=ConceptRepresentationFormat.SCHEMA,
            is_multiple=True,
        )

        assert result["concept"] == "test.SimpleContent"
        # The content should be wrapped in an array schema
        assert result["content"]["type"] == "array"
        assert "items" in result["content"]
        # The items should be the original schema
        assert result["content"]["items"]["type"] == "object"
        assert "properties" in result["content"]["items"]
        assert "name" in result["content"]["items"]["properties"]
        assert "count" in result["content"]["items"]["properties"]
        assert imports == set()

    def test_schema_nested_content_multiple(self) -> None:
        """Schema for nested content with multiple items wraps correctly."""
        concept = Concept(
            code="ContentWithNestedClass",
            domain_code="test",
            description="Test concept with nested class",
            structure_class_name="ContentWithNestedClass",
        )

        result, _ = concept.render_concept_representation(
            structure_class=ContentWithNestedClass,
            output_format=ConceptRepresentationFormat.SCHEMA,
            is_multiple=True,
        )

        assert result["concept"] == "test.ContentWithNestedClass"
        # The content should be wrapped in an array schema
        assert result["content"]["type"] == "array"
        assert "items" in result["content"]
        # The items should contain the nested structure
        items_schema = result["content"]["items"]
        assert items_schema["type"] == "object"
        assert "properties" in items_schema


# =============================================================================
# Tests for NumberContent (native Number concept)
# =============================================================================


class TestNumberContentRepresentation:
    """Test that NumberContent generates proper numeric values, not string placeholders.

    NumberContent has a field 'number: int | float' which is a union type.
    The generator should produce a numeric value (1), not 'number_int | float'.
    """

    def test_number_content_json_representation(self) -> None:
        """NumberContent generates proper numeric value in JSON format."""
        from pipelex.core.stuffs.number_content import NumberContent  # noqa: PLC0415

        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(NumberContent)

        assert isinstance(result, dict)
        assert "number" in result
        assert isinstance(result["number"], (int, float)), f"Expected numeric value, got {type(result['number'])}: {result['number']}"
        assert result["number"] == 1

    def test_number_content_python_representation(self) -> None:
        """NumberContent generates proper numeric value in Python format."""
        from pipelex.core.stuffs.number_content import NumberContent  # noqa: PLC0415

        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(NumberContent)

        # Should be "NumberContent(number=1)" not "NumberContent(number=\"number_int | float\")"
        assert isinstance(result, str)
        assert "number=1" in result, f"Expected 'number=1' in result, got: {result}"
        assert "number_int" not in result, f"Should not contain string placeholder: {result}"


# =============================================================================
# Tests for DateContent (native Date concept)
# =============================================================================


class TestDateContentRepresentation:
    """Test that DateContent generates a round-trippable ISO date example.

    DateContent has a required 'date: datetime.date' field. With include_optional=False (the
    `pipelex build inputs` path), only that field is emitted, and its example must parse back
    into a DateContent so the `build inputs` -> `run` round-trip holds (not a 'date_date' placeholder).
    """

    def test_date_content_json_representation_round_trips(self) -> None:
        """The JSON template for a Date input parses back into a DateContent."""
        from pipelex.core.stuffs.date_content import DateContent  # noqa: PLC0415

        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_representation("native.Date", structure_class=DateContent, include_optional=False)

        content = result["content"]
        assert isinstance(content, dict)
        assert "date" in content
        # include_optional=False omits the optional `time`: the build-inputs template must never
        # fabricate a time (the Date concept's source-precision contract).
        assert "time" not in content
        # The emitted example must be a real ISO date the DateContent accepts (round-trip).
        rebuilt = DateContent.model_validate(content)
        assert isinstance(rebuilt.date, datetime.date)

    def test_date_content_python_representation_has_no_placeholder(self) -> None:
        """The Python template for a Date input carries no 'date_date' placeholder."""
        from pipelex.core.stuffs.date_content import DateContent  # noqa: PLC0415

        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_representation("native.Date", structure_class=DateContent, include_optional=False)

        content = result["content"]
        assert isinstance(content, str)
        assert "date_date" not in content, f"Should not contain string placeholder: {content}"
