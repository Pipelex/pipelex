"""Unit tests for Literal type handling in DryRunFactory."""

from typing import Literal

import pytest
from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory

# =============================================================================
# Test Fixtures
# =============================================================================

TONE_CHOICES = ("Casual", "Professional", "Humorous", "Academic")
LENGTH_CHOICES = ("Short", "Medium", "Long")


class ModelWithLiteral(BaseModel):
    """Model with a required Literal field."""

    tone: Literal["Casual", "Professional", "Humorous", "Academic"] = Field(..., description="Writing tone")


class ModelWithMultipleLiterals(BaseModel):
    """Model with multiple Literal fields and a plain string field."""

    tone: Literal["Casual", "Professional", "Humorous", "Academic"] = Field(..., description="Writing tone")
    length: Literal["Short", "Medium", "Long"] = Field(..., description="Article length")
    topic: str = Field(..., description="The topic")


class ModelWithOptionalLiteral(BaseModel):
    """Model with an optional Literal field."""

    category: Literal["electronics", "clothing", "food"] | None = Field(None, description="Product category")


class ModelWithRequiredAndOptionalLiteral(BaseModel):
    """Model with a required Literal and an optional Literal."""

    status: Literal["draft", "published", "archived"] = Field(..., description="Status")
    priority: Literal["low", "medium", "high"] | None = Field(None, description="Priority")


class ParentModelWithNestedLiteral(BaseModel):
    """Parent model containing a nested model with Literal fields."""

    name: str = Field(..., description="Name")
    child: ModelWithLiteral = Field(..., description="Nested model")


# =============================================================================
# Tests
# =============================================================================


class TestDryRunFactoryLiteralTypes:
    """Test that DryRunFactory generates valid values for Literal type fields."""

    def test_factory_build_with_literal_field(self) -> None:
        """Factory generates valid Literal values when building a model."""
        factory = DryRunFactory.make_dry_run_factory(ModelWithLiteral)
        instance = factory.build()
        assert instance.tone in TONE_CHOICES, f"Expected one of {TONE_CHOICES}, got {instance.tone!r}"

    def test_factory_build_with_multiple_literals(self) -> None:
        """Factory generates valid values for all Literal fields."""
        factory = DryRunFactory.make_dry_run_factory(ModelWithMultipleLiterals)
        instance = factory.build()
        assert instance.tone in TONE_CHOICES
        assert instance.length in LENGTH_CHOICES
        assert isinstance(instance.topic, str)

    @pytest.mark.parametrize(
        ("topic", "model_class", "field_name", "valid_choices"),
        [
            ("required literal", ModelWithLiteral, "tone", TONE_CHOICES),
            ("optional literal", ModelWithOptionalLiteral, "category", ("electronics", "clothing", "food")),
            ("required with optional sibling", ModelWithRequiredAndOptionalLiteral, "status", ("draft", "published", "archived")),
        ],
    )
    def test_factory_build_various_literal_models(
        self,
        topic: str,
        model_class: type[BaseModel],
        field_name: str,
        valid_choices: tuple[str, ...],
    ) -> None:
        """Factory produces valid Literal values for different model configurations."""
        factory = DryRunFactory.make_dry_run_factory(model_class)
        instance = factory.build()
        value = getattr(instance, field_name)
        assert value in valid_choices, f"[{topic}] Expected one of {valid_choices} for {field_name}, got {value!r}"

    def test_factory_build_with_construct_still_valid(self) -> None:
        """Factory with factory_use_construct=True still gets valid Literal values."""
        factory = DryRunFactory.make_dry_run_factory(ModelWithLiteral)
        instance = factory.build(factory_use_construct=True)
        assert instance.tone in TONE_CHOICES, f"Expected valid tone even with construct, got {instance.tone!r}"

    def test_factory_build_no_validation_error(self) -> None:
        """Factory build without factory_use_construct does not raise ValidationError for Literal fields."""
        factory = DryRunFactory.make_dry_run_factory(ModelWithMultipleLiterals)
        # This should NOT raise a ValidationError
        instance = factory.build()
        assert instance.tone in TONE_CHOICES
        assert instance.length in LENGTH_CHOICES

    def test_nested_model_with_literal(self) -> None:
        """Factory generates valid Literal values for nested models."""
        factory = DryRunFactory.make_dry_run_factory(ParentModelWithNestedLiteral)
        instance = factory.build(factory_use_construct=True)
        assert instance.child.tone in TONE_CHOICES, f"Expected valid tone in nested model, got {instance.child.tone!r}"
