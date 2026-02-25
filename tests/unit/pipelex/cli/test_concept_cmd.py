"""Unit tests for the agent CLI concept command."""

from __future__ import annotations

import json
from typing import Any

from pipelex.builder.concept.concept_spec import ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.cli.agent_cli.commands.concept_cmd import (
    _concept_spec_to_toml,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
    _parse_concept_spec_from_json,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
    _structure_field_to_dict,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)


class TestStructureFieldToDict:
    """Tests for _structure_field_to_dict function."""

    def test_text_field_with_description_only(self) -> None:
        """Text field with only description should produce minimal dict."""
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="The person's name",
            type=ConceptStructureSpecFieldType.TEXT,
        )
        result = _structure_field_to_dict(field_spec)

        assert result == {"description": "The person's name"}
        assert "type" not in result

    def test_text_field_with_required(self) -> None:
        """Text field with required=True should include type."""
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="The person's name",
            type=ConceptStructureSpecFieldType.TEXT,
            required=True,
        )
        result = _structure_field_to_dict(field_spec)

        assert result["description"] == "The person's name"
        assert result["type"] == ConceptStructureSpecFieldType.TEXT
        assert result["required"] is True

    def test_integer_field(self) -> None:
        """Integer field should include type."""
        field_spec = ConceptStructureSpec(
            the_field_name="age",
            description="Age in years",
            type=ConceptStructureSpecFieldType.INTEGER,
        )
        result = _structure_field_to_dict(field_spec)

        assert result["type"] == ConceptStructureSpecFieldType.INTEGER
        assert result["description"] == "Age in years"

    def test_field_with_default_value(self) -> None:
        """Field with default value should include default."""
        field_spec = ConceptStructureSpec(
            the_field_name="count",
            description="Number of items",
            type=ConceptStructureSpecFieldType.INTEGER,
            default_value=0,
        )
        result = _structure_field_to_dict(field_spec)

        assert result["default"] == 0
        assert result["type"] == ConceptStructureSpecFieldType.INTEGER

    def test_concept_field_with_concept_ref(self) -> None:
        """Concept field should include concept_ref."""
        field_spec = ConceptStructureSpec(
            the_field_name="customer",
            description="The customer",
            type=ConceptStructureSpecFieldType.CONCEPT,
            concept_ref="myapp.Customer",
        )
        result = _structure_field_to_dict(field_spec)

        assert result["concept_ref"] == "myapp.Customer"
        assert result["type"] == ConceptStructureSpecFieldType.CONCEPT

    def test_field_with_choices(self) -> None:
        """Field with choices should include choices in output.

        This test would have caught the bug where choices were silently dropped.
        """
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["pending", "in_progress", "complete"],
        )
        result = _structure_field_to_dict(field_spec)

        assert result["choices"] == ["pending", "in_progress", "complete"]
        assert result["description"] == "Current status"

    def test_field_with_choices_and_required(self) -> None:
        """Field with choices and required should include both."""
        field_spec = ConceptStructureSpec(
            the_field_name="priority",
            description="Task priority",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["low", "medium", "high"],
            required=True,
        )
        result = _structure_field_to_dict(field_spec)

        assert result["choices"] == ["low", "medium", "high"]
        assert result["required"] is True
        assert result["type"] == ConceptStructureSpecFieldType.TEXT

    def test_field_with_choices_and_default(self) -> None:
        """Field with choices and default value should include both."""
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["active", "inactive", "pending"],
            default_value="pending",
        )
        result = _structure_field_to_dict(field_spec)

        assert result["choices"] == ["active", "inactive", "pending"]
        assert result["default"] == "pending"


class TestParseConceptSpecFromJson:
    """Tests for _parse_concept_spec_from_json function."""

    def test_parse_simple_concept_with_refines(self) -> None:
        """Parse a simple concept that refines Text."""
        spec_data: dict[str, Any] = {
            "the_concept_code": "Invoice",
            "description": "A commercial invoice",
            "refines": "Text",
        }
        result = _parse_concept_spec_from_json(spec_data)

        assert result.the_concept_code == "Invoice"
        assert result.description == "A commercial invoice"
        assert result.refines == "Text"

    def test_parse_structured_concept(self) -> None:
        """Parse a concept with structure."""
        spec_data: dict[str, Any] = {
            "the_concept_code": "Person",
            "description": "A person record",
            "structure": {
                "name": "The person's name",
                "age": {"type": "integer", "description": "Age in years"},
            },
        }
        result = _parse_concept_spec_from_json(spec_data)

        assert result.the_concept_code == "Person"
        assert result.structure is not None
        assert "name" in result.structure
        assert "age" in result.structure
        assert result.structure["name"].type == ConceptStructureSpecFieldType.TEXT
        assert result.structure["age"].type == ConceptStructureSpecFieldType.INTEGER

    def test_parse_concept_with_choices_in_structure(self) -> None:
        """Parse a concept with choices field in structure.

        This test would have caught the bug where choices were silently ignored
        during JSON parsing (if Pydantic had extra='ignore').
        """
        spec_data: dict[str, Any] = {
            "the_concept_code": "Task",
            "description": "A task with status",
            "structure": {
                "status": {
                    "type": "text",
                    "description": "Current status",
                    "choices": ["pending", "in_progress", "complete"],
                }
            },
        }
        result = _parse_concept_spec_from_json(spec_data)

        assert result.structure is not None
        assert result.structure["status"].choices == ["pending", "in_progress", "complete"]


class TestConceptSpecToToml:
    """Tests for _concept_spec_to_toml function."""

    def test_toml_output_includes_choices(self) -> None:
        """TOML output should include choices when present.

        This is the main regression test for the bug where choices
        were not included in the TOML output.
        """
        spec_data: dict[str, Any] = {
            "the_concept_code": "TaskStatus",
            "description": "A task with status tracking",
            "structure": {
                "status": {
                    "type": "text",
                    "description": "Current status",
                    "choices": ["pending", "in_progress", "complete"],
                }
            },
        }
        concept_spec = _parse_concept_spec_from_json(spec_data)
        toml_output = _concept_spec_to_toml(concept_spec)

        assert 'choices = ["pending", "in_progress", "complete"]' in toml_output

    def test_toml_output_simple_refines_concept(self) -> None:
        """TOML output for a simple refines concept."""
        spec_data: dict[str, Any] = {
            "the_concept_code": "Invoice",
            "description": "A commercial invoice",
            "refines": "Text",
        }
        concept_spec = _parse_concept_spec_from_json(spec_data)
        toml_output = _concept_spec_to_toml(concept_spec)

        assert "[concept.Invoice]" in toml_output
        assert 'description = "A commercial invoice"' in toml_output
        assert 'refines = "Text"' in toml_output

    def test_toml_output_structured_concept_with_multiple_fields(self) -> None:
        """TOML output for a structured concept with multiple field types."""
        spec_data: dict[str, Any] = {
            "the_concept_code": "Order",
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
        concept_spec = _parse_concept_spec_from_json(spec_data)
        toml_output = _concept_spec_to_toml(concept_spec)

        assert "[concept.Order]" in toml_output
        assert "order_id" in toml_output
        assert "required = true" in toml_output
        assert "quantity" in toml_output
        assert "status" in toml_output
        assert "choices" in toml_output


class TestConceptStructureSpecChoices:
    """Tests specifically for the choices field on ConceptStructureSpec."""

    def test_choices_field_exists_on_model(self) -> None:
        """Verify that choices field exists on ConceptStructureSpec."""
        field_spec = ConceptStructureSpec(
            the_field_name="status",
            description="Current status",
            type=ConceptStructureSpecFieldType.TEXT,
            choices=["a", "b", "c"],
        )
        assert hasattr(field_spec, "choices")
        assert field_spec.choices == ["a", "b", "c"]

    def test_choices_none_by_default(self) -> None:
        """Choices should be None by default."""
        field_spec = ConceptStructureSpec(
            the_field_name="name",
            description="A name",
            type=ConceptStructureSpecFieldType.TEXT,
        )
        assert field_spec.choices is None

    def test_choices_passed_to_blueprint(self) -> None:
        """Choices should be passed through to the blueprint."""
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
                "the_concept_code": "WorkItem",
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
        concept_spec = _parse_concept_spec_from_json(spec_data)
        toml_output = _concept_spec_to_toml(concept_spec)

        assert 'choices = ["low", "medium", "high", "critical"]' in toml_output
        assert "required = true" in toml_output
