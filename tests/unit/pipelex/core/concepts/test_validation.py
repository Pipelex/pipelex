"""Tests for concept validation functions."""

import pytest

from pipelex.core.concepts.validation import (
    is_concept_code_valid,
    is_concept_ref_or_code_valid,
    is_concept_ref_valid,
)


class TestConceptValidation:
    """Test concept validation functions."""

    @pytest.mark.parametrize(
        ("concept_code", "expected"),
        [
            ("Text", True),
            ("MyCustomConcept", True),
            ("A", True),
            ("AB", True),
            ("text", False),
            ("myCustomConcept", False),
            ("my_custom_concept", False),
            ("MY_CUSTOM_CONCEPT", False),
            ("123Concept", False),
            ("", False),
        ],
    )
    def test_is_concept_code_valid(self, concept_code: str, expected: bool):
        """Test is_concept_code_valid validates PascalCase concept codes."""
        assert is_concept_code_valid(concept_code=concept_code) == expected

    @pytest.mark.parametrize(
        ("concept_ref", "expected"),
        [
            ("native.Text", True),
            ("myapp.BaseEntity", True),
            ("crm.Customer", True),
            ("my_app.Entity", True),
            ("domain.A", True),
            # Hierarchical domains
            ("legal.contracts.NonCompeteClause", True),
            ("legal.contracts.shareholder.Agreement", True),
            ("a.b.c.D", True),
            # Invalid
            ("native.text", False),
            ("NATIVE.Text", False),
            ("my-app.Entity", False),
            ("domain.lowercase", False),
            (".Text", False),
            ("domain.", False),
        ],
    )
    def test_is_concept_ref_valid(self, concept_ref: str, expected: bool):
        """Test is_concept_ref_valid validates domain.ConceptCode format."""
        assert is_concept_ref_valid(concept_ref=concept_ref) == expected

    @pytest.mark.parametrize(
        ("concept_ref_or_code", "expected"),
        [
            # Valid concept codes (PascalCase)
            ("Text", True),
            ("MyCustomConcept", True),
            ("Image", True),
            # Valid concept refs (domain.ConceptCode)
            ("native.Text", True),
            ("myapp.BaseEntity", True),
            ("crm.Customer", True),
            ("my_app.Entity", True),
            # Valid - hierarchical domain refs (now supported)
            ("org.dept.team.Entity", True),
            ("a.b.c.D", True),
            ("legal.contracts.NonCompeteClause", True),
            # Invalid - lowercase bare code
            ("somecustomconcept", False),
            ("text", False),
            # Invalid - hyphenated domain
            ("my-app.Entity", False),
            # Invalid - empty string
            ("", False),
        ],
    )
    def test_is_concept_ref_or_code_valid(self, concept_ref_or_code: str, expected: bool):
        """Test is_concept_ref_or_code_valid validates both formats."""
        assert is_concept_ref_or_code_valid(concept_ref_or_code=concept_ref_or_code) == expected
