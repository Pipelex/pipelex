"""Unit tests for parse_concept_spec from pipelex.builder.operations.concept_ops."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from pipelex.builder.concept.concept_spec import ConceptStructureSpecFieldType
from pipelex.builder.operations.concept_ops import parse_concept_spec


class TestParseConceptSpec:
    """Comprehensive tests for parse_concept_spec: validation, aliases, structure conversion."""

    _BASE: ClassVar[dict[str, Any]] = {
        "description": "A test concept",
        "refines": "Text",
    }

    # -- concept_code aliases ---------------------------------------------

    def test_canonical_concept_code(self) -> None:
        spec = {**self._BASE, "concept_code": "Invoice"}
        result = parse_concept_spec(spec)
        assert result.concept_code == "Invoice"

    @pytest.mark.parametrize("alias", ["the_concept_code", "code", "name", "concept_name", "concept_ref"])
    def test_concept_code_alias_accepted(self, alias: str) -> None:
        spec = {**self._BASE, alias: "Invoice"}
        result = parse_concept_spec(spec)
        assert result.concept_code == "Invoice"

    def test_canonical_ignores_alias(self) -> None:
        """When concept_code is present, alias keys are removed."""
        spec = {**self._BASE, "concept_code": "Canonical", "name": "Alias"}
        result = parse_concept_spec(spec)
        assert result.concept_code == "Canonical"

    def test_multiple_aliases_all_cleaned_up(self) -> None:
        spec = {**self._BASE, "concept_code": "Invoice", "name": "Alt", "code": "Alt2"}
        result = parse_concept_spec(spec)
        assert result.concept_code == "Invoice"

    # -- does not mutate caller's dict ------------------------------------

    def test_original_dict_unchanged(self) -> None:
        original: dict[str, Any] = {**self._BASE, "code": "Invoice"}
        snapshot = dict(original)
        parse_concept_spec(original)
        assert original == snapshot

    # -- structure field conversion ---------------------------------------

    def test_string_field_becomes_text(self) -> None:
        """A bare string in structure should be treated as a text field."""
        spec: dict[str, Any] = {
            "concept_code": "Simple",
            "description": "A simple concept",
            "structure": {"title": "The title of the item"},
        }
        result = parse_concept_spec(spec)
        assert result.structure is not None
        assert result.structure["title"].type == ConceptStructureSpecFieldType.TEXT
        assert result.structure["title"].description == "The title of the item"

    def test_mixed_string_and_dict_fields(self) -> None:
        spec: dict[str, Any] = {
            "concept_code": "Mixed",
            "description": "A mixed concept",
            "structure": {
                "name": "The person's name",
                "age": {"type": "integer", "description": "Age in years"},
            },
        }
        result = parse_concept_spec(spec)
        assert result.structure is not None
        assert result.structure["name"].type == ConceptStructureSpecFieldType.TEXT
        assert result.structure["age"].type == ConceptStructureSpecFieldType.INTEGER

    # -- full parsing scenarios -------------------------------------------

    def test_simple_concept_with_refines(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Invoice",
            "description": "A commercial invoice",
            "refines": "Text",
        }
        result = parse_concept_spec(spec_data)
        assert result.concept_code == "Invoice"
        assert result.description == "A commercial invoice"
        assert result.refines == "Text"

    def test_structured_concept(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Person",
            "description": "A person record",
            "structure": {
                "name": "The person's name",
                "age": {"type": "integer", "description": "Age in years"},
            },
        }
        result = parse_concept_spec(spec_data)
        assert result.concept_code == "Person"
        assert result.structure is not None
        assert "name" in result.structure
        assert "age" in result.structure

    def test_concept_with_choices_in_structure(self) -> None:
        spec_data: dict[str, Any] = {
            "concept_code": "Task",
            "description": "A task with status",
            "structure": {
                "status": {
                    "type": "text",
                    "description": "Current status",
                    "choices": ["pending", "in_progress", "complete"],
                }
            },
        }
        result = parse_concept_spec(spec_data)
        assert result.structure is not None
        assert result.structure["status"].choices == ["pending", "in_progress", "complete"]
