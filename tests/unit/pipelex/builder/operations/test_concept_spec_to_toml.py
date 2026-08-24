"""Unit tests for concept_spec_to_toml and structure_field_to_dict from concept_ops."""

from __future__ import annotations

import json
import tomllib
from typing import Any

from pipelex.builder.concept.concept_spec import ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.builder.operations.concept_ops import (
    concept_spec_to_toml,
    parse_concept_spec,
    structure_field_to_dict,
)
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint


class TestConceptSpecToToml:
    """Tests for structure_field_to_dict and concept_spec_to_toml covering all field types and modes."""

    # -- structure_field_to_dict ------------------------------------------

    def test_text_field_description_only(self) -> None:
        """Text field with only description should produce minimal dict."""
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="The person's name",
            type=ConceptStructureSpecFieldType.TEXT,
        )
        result = structure_field_to_dict(field_spec)
        assert result == {"description": "The person's name"}
        assert "type" not in result

    def test_text_field_with_required(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="The person's name",
            type=ConceptStructureSpecFieldType.TEXT,
            required=True,
        )
        result = structure_field_to_dict(field_spec)
        assert result["type"] == ConceptStructureSpecFieldType.TEXT
        assert result["required"] is True

    def test_integer_field(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="age",
            description="Age in years",
            type=ConceptStructureSpecFieldType.INTEGER,
        )
        result = structure_field_to_dict(field_spec)
        assert result["type"] == ConceptStructureSpecFieldType.INTEGER
        assert result["description"] == "Age in years"

    def test_field_with_default_value(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="count",
            description="Number of items",
            type=ConceptStructureSpecFieldType.INTEGER,
            default_value=0,
        )
        result = structure_field_to_dict(field_spec)
        assert result["default_value"] == 0, "The language key is default_value — `default` evaporates on re-load (E8)"

    def test_concept_field_with_concept_ref(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="customer",
            description="The customer",
            type=ConceptStructureSpecFieldType.CONCEPT,
            concept_ref="myapp.Customer",
        )
        result = structure_field_to_dict(field_spec)
        assert result["concept_ref"] == "myapp.Customer"

    def test_field_with_choices(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["pending", "in_progress", "complete"],
        )
        result = structure_field_to_dict(field_spec)
        assert result["choices"] == ["pending", "in_progress", "complete"]

    def test_field_with_choices_and_required(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="priority",
            description="Task priority",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["low", "medium", "high"],
            required=True,
        )
        result = structure_field_to_dict(field_spec)
        assert result["choices"] == ["low", "medium", "high"]
        assert result["required"] is True

    def test_field_with_choices_and_default(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["active", "inactive", "pending"],
            default_value="pending",
        )
        result = structure_field_to_dict(field_spec)
        assert result["choices"] == ["active", "inactive", "pending"]
        assert result["default_value"] == "pending"

    # -- concept_spec_to_toml ---------------------------------------------

    def test_simple_refines_concept(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Invoice",
            "description": "A commercial invoice",
            "refines": "Text",
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert "[concept.Invoice]" in toml_output
        assert 'description = "A commercial invoice"' in toml_output
        assert 'refines = "Text"' in toml_output

    def test_structured_concept_with_multiple_fields(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Order",
            "description": "A customer order",
            "structure": {
                "order_id": {"type": "text", "description": "Order identifier", "required": True},
                "quantity": {"type": "integer", "description": "Number of items"},
                "status": {
                    "type": "text",
                    "description": "Order status",
                    "choices": ["pending", "shipped", "delivered"],
                },
            },
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert "[concept.Order]" in toml_output
        assert "order_id" in toml_output
        assert "required = true" in toml_output
        assert "quantity" in toml_output
        assert "choices" in toml_output

    def test_toml_includes_choices(self) -> None:
        """Regression: choices must appear in TOML output."""
        spec_data: dict[str, Any] = {
            "concept_code": "TaskStatus",
            "description": "A task with status tracking",
            "structure": {
                "status": {
                    "type": "text",
                    "description": "Current status",
                    "choices": ["pending", "in_progress", "complete"],
                }
            },
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert 'choices = ["pending", "in_progress", "complete"]' in toml_output

    def test_choices_none_by_default(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="A name",
            type=ConceptStructureSpecFieldType.TEXT,
        )
        assert field_spec.choices is None

    def test_choices_passed_to_blueprint(self) -> None:
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["pending", "complete"],
        )
        blueprint = field_spec.to_blueprint()
        assert blueprint.choices == ["pending", "complete"]

    def test_roundtrip_json_to_toml_preserves_choices(self) -> None:
        """Full roundtrip from JSON input to TOML output should preserve choices."""
        input_json = json.dumps(
            {
                "concept_code": "WorkItem",
                "description": "A work item",
                "structure": {
                    "priority": {
                        "type": "text",
                        "description": "Priority level",
                        "choices": ["low", "medium", "high", "critical"],
                        "required": True,
                    }
                },
            }
        )
        spec_data = json.loads(input_json)
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert 'choices = ["low", "medium", "high", "critical"]' in toml_output
        assert "required = true" in toml_output

    def test_description_only_field_uses_string_format(self) -> None:
        """A field with only a description should serialize as a simple string in TOML."""
        spec_data: dict[str, Any] = {
            "concept_code": "Simple",
            "description": "A concept with simple fields",
            "structure": {"title": "The title"},
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert 'title = "The title"' in toml_output

    def test_no_structure_omits_structure_section(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Plain",
            "description": "A plain concept",
            "refines": "Text",
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert "structure" not in toml_output

    def test_builder_toml_roundtrips_through_blueprint_with_default(self) -> None:
        """Write-then-validate round trip (E8): a builder-authored default must survive re-load as a
        blueprint — the builder once wrote the key `default`, which the language does not read, so
        the fact evaporated silently. E7's forbid now turns any recurrence into a hard failure.
        """
        spec_data: dict[str, Any] = {
            "concept_code": "Counter",
            "description": "A counter with a default",
            "structure": {
                "count": {"type": "integer", "description": "Number of items", "default_value": 7},
                "label": {"type": "text", "description": "A label", "required": True},
            },
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        reloaded = tomllib.loads(toml_output)
        blueprint = ConceptBlueprint.model_validate(reloaded["concept"]["Counter"])
        assert isinstance(blueprint.structure, dict)
        count_field = blueprint.structure["count"]
        assert isinstance(count_field, ConceptStructureBlueprint)
        assert count_field.default_value == 7, "The authored default must survive the write-then-validate loop"
        label_field = blueprint.structure["label"]
        assert isinstance(label_field, ConceptStructureBlueprint)
        assert label_field.required is True

    def test_no_refines_omits_refines(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Standalone",
            "description": "A standalone concept",
            "structure": {"name": "The name"},
        }
        concept_spec = parse_concept_spec(spec_data)
        toml_output = concept_spec_to_toml(concept_spec)
        assert "refines" not in toml_output
