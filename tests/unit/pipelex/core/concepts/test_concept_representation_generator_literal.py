"""Unit tests for Literal type handling in ConceptRepresentationGenerator."""

from typing import Literal

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
)
from pipelex.core.stuffs.structured_content import StructuredContent

# =============================================================================
# Test Fixtures
# =============================================================================

TONE_CHOICES = ("Casual", "Professional", "Humorous", "Academic")
LENGTH_CHOICES = ("Short", "Medium", "Long")


class ContentWithLiteral(StructuredContent):
    """Content with a Literal field (simulates a structure field with choices)."""

    tone: Literal["Casual", "Professional", "Humorous", "Academic"] = Field(..., description="Writing tone")


class ContentWithMultipleLiterals(StructuredContent):
    """Content with multiple Literal fields."""

    tone: Literal["Casual", "Professional", "Humorous", "Academic"] = Field(..., description="Writing tone")
    length: Literal["Short", "Medium", "Long"] = Field(..., description="Article length")
    topic: str = Field(..., description="The topic")


class ContentWithOptionalLiteral(StructuredContent):
    """Content with an optional Literal field."""

    category: Literal["electronics", "clothing", "food"] | None = Field(None, description="Product category")


class ContentWithRequiredAndOptionalLiteral(StructuredContent):
    """Content with a required Literal and an optional Literal."""

    status: Literal["draft", "published", "archived"] = Field(..., description="Status")
    priority: Literal["low", "medium", "high"] | None = Field(None, description="Priority")


# =============================================================================
# Tests
# =============================================================================


class TestGenerateFieldValueLiteralTypes:
    """Test generate_field_value for Literal types (fields with choices)."""

    def test_literal_field_returns_one_of_the_choices(self) -> None:
        """Literal field generates one of the valid literal values."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(
            Literal["Casual", "Professional", "Humorous", "Academic"],
            "tone",
        )
        assert result in TONE_CHOICES, f"Expected one of {TONE_CHOICES}, got {result!r}"

    def test_literal_field_returns_string_not_placeholder(self) -> None:
        """Literal field returns an actual choice, not a placeholder like 'tone_typing.Literal[...]'."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(
            Literal["Short", "Medium", "Long"],
            "length",
        )
        assert result in LENGTH_CHOICES
        assert "Literal" not in str(result), f"Should not contain 'Literal' placeholder, got {result!r}"
        assert "typing" not in str(result), f"Should not contain 'typing' placeholder, got {result!r}"

    def test_optional_literal_field_returns_one_of_the_choices(self) -> None:
        """Optional[Literal[...]] unwraps and returns one of the valid values."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(
            Literal["electronics", "clothing", "food"] | None,
            "category",
        )
        assert result in {"electronics", "clothing", "food"}, f"Expected a valid choice, got {result!r}"

    @pytest.mark.parametrize(
        ("topic", "literal_type", "valid_choices"),
        [
            ("string choices", Literal["a", "b", "c"], ("a", "b", "c")),
            ("single choice", Literal["only_option"], ("only_option",)),
        ],
    )
    def test_literal_with_various_choices(
        self,
        topic: str,
        literal_type: type,
        valid_choices: tuple[str, ...],
    ) -> None:
        """Literal fields with different sets of choices all generate valid values."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_field_value(literal_type, "field")
        assert result in valid_choices, f"[{topic}] Expected one of {valid_choices}, got {result!r}"

    def test_class_with_literal_field_json(self) -> None:
        """Class with a Literal field generates a valid choice in JSON format."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithLiteral)
        assert isinstance(result, dict)
        assert "tone" in result
        assert result["tone"] in TONE_CHOICES, f"Expected one of {TONE_CHOICES}, got {result['tone']!r}"

    def test_class_with_literal_field_python(self) -> None:
        """Class with a Literal field generates a valid choice in Python format."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        result = generator.generate_class_representation(ContentWithLiteral)
        assert isinstance(result, str)
        assert "ContentWithLiteral(tone=" in result
        # The tone value should be one of the choices, quoted
        has_valid_choice = any(f'tone="{choice}"' in result for choice in TONE_CHOICES)
        assert has_valid_choice, f"Expected a valid choice in Python format, got {result!r}"

    def test_class_with_multiple_literals_json(self) -> None:
        """Class with multiple Literal fields generates valid choices for each."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(ContentWithMultipleLiterals)
        assert isinstance(result, dict)
        assert result["tone"] in TONE_CHOICES
        assert result["length"] in LENGTH_CHOICES
        assert result["topic"] == "topic_value"

    def test_exclude_optional_literal_field(self) -> None:
        """Optional Literal fields are excluded when include_optional=False."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(
            ContentWithRequiredAndOptionalLiteral,
            include_optional=False,
        )
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in {"draft", "published", "archived"}
        assert "priority" not in result

    def test_include_optional_literal_field(self) -> None:
        """Optional Literal fields are included when include_optional=True."""
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.JSON)
        result = generator.generate_class_representation(
            ContentWithRequiredAndOptionalLiteral,
            include_optional=True,
        )
        assert isinstance(result, dict)
        assert result["status"] in {"draft", "published", "archived"}
        assert result["priority"] in {"low", "medium", "high"}
