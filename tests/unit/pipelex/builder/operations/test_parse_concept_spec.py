"""Unit tests for parse_concept_spec from pipelex.builder.operations.concept_ops."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import error_domain_is_input
from pipelex.builder.concept.concept_spec import ConceptStructureSpecFieldType
from pipelex.builder.concept.exceptions import ConceptSpecError
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

    def test_missing_concept_code_raises(self) -> None:
        """Spec with no concept_code and no alias should raise ValidationError."""
        spec: dict[str, Any] = {**self._BASE}
        with pytest.raises(ValidationError):
            parse_concept_spec(spec)

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

    def test_dict_field_without_type_defaults_to_text(self) -> None:
        """When agent provides a dict field spec but omits 'type', it should default to text."""
        spec: dict[str, Any] = {
            "concept_code": "MatchAnalysis",
            "description": "Analysis of CV-job match",
            "structure": {
                "matching_strengths": {"description": "Key areas where CV aligns", "required": True},
                "gaps": {"description": "Areas where CV falls short", "required": True},
                "summary": {"description": "Brief overall assessment"},
            },
        }
        result = parse_concept_spec(spec)
        assert result.structure is not None
        for field_name in ("matching_strengths", "gaps", "summary"):
            assert result.structure[field_name].type == ConceptStructureSpecFieldType.TEXT
        assert result.structure["matching_strengths"].required is True
        assert result.structure["summary"].required is False

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

    # -- malformed structure shape (typed, not bare AttributeError/TypeError) --

    # A present-but-falsy non-mapping (``[]`` / ``""`` / ``0`` / ``False``) must hit the
    # typed guard too, not slip past a truthiness check into a bare Pydantic ValidationError.
    @pytest.mark.parametrize("bad_structure", ["not_a_dict", [], "", 0, False])
    def test_non_dict_structure_raises_concept_spec_error(self, bad_structure: Any) -> None:
        """A non-mapping ``structure`` is a caller-input fault, not a bare AttributeError/ValidationError."""
        spec: dict[str, Any] = {"concept_code": "Bad", "description": "d", "structure": bad_structure}
        with pytest.raises(ConceptSpecError, match="'structure' must be a mapping"):
            parse_concept_spec(spec)

    def test_none_structure_is_treated_as_absent(self) -> None:
        """``structure: None`` means "no structure" (the field defaults to None), not a malformed mapping."""
        spec: dict[str, Any] = {"concept_code": "NoStruct", "description": "d", "refines": "Text", "structure": None}
        result = parse_concept_spec(spec)
        assert result.structure is None

    @pytest.mark.parametrize("bad_field_value", [42, [1, 2], 3.14, True])
    def test_non_str_non_dict_field_raises_concept_spec_error(self, bad_field_value: Any) -> None:
        """A structure field that is neither a description string nor a field-spec mapping is a typed input error."""
        spec: dict[str, Any] = {"concept_code": "Bad", "description": "d", "structure": {"my_field": bad_field_value}}
        with pytest.raises(ConceptSpecError, match="must be a description string or a field-spec mapping"):
            parse_concept_spec(spec)

    def test_malformed_structure_classifies_as_input_domain(self) -> None:
        """The raised error carries the INPUT domain so HTTP consumers render it as a 422."""
        spec: dict[str, Any] = {"concept_code": "Bad", "description": "d", "structure": "not_a_dict"}
        with pytest.raises(ConceptSpecError) as exc_info:
            parse_concept_spec(spec)
        assert error_domain_is_input(exc_info.value.error_domain)

    # -- malformed top-level shape (typed, not bare TypeError/ValueError) --

    @pytest.mark.parametrize("bad_spec", ["a string", ["a", "b"], 123, 3.14, None])
    def test_non_mapping_top_level_raises_concept_spec_error(self, bad_spec: Any) -> None:
        """A non-mapping top-level spec leaks a bare TypeError/ValueError from dict() without the guard."""
        with pytest.raises(ConceptSpecError, match="must be a mapping"):
            parse_concept_spec(bad_spec)

    def test_non_mapping_top_level_classifies_as_input_domain(self) -> None:
        with pytest.raises(ConceptSpecError) as exc_info:
            parse_concept_spec("not a mapping")
        assert error_domain_is_input(exc_info.value.error_domain)

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
