import pytest

from pipelex.core.concept import Concept
from pipelex.exceptions import ConceptCodeError, ConceptDomainError, ConceptError


class TestConceptRefinesValidation:
    def test_validate_refines_success(self):
        # Test valid refines list
        valid_refines = ["domain1.Concept1", "domain2.Concept2"]
        result = Concept.validate_refines(valid_refines)
        assert result == valid_refines

    def test_validate_refines_empty_list(self):
        # Test empty refines list
        result = Concept.validate_refines([])
        assert result == []

    def test_validate_refines_missing_dot(self):
        # Test refines with missing dot
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept.validate_refines(["invalidConcept"])
        assert "Each refine code must contain a single dot" in str(exc_info.value)

    def test_validate_refines_invalid_domain(self):
        # Test refines with invalid domain format
        with pytest.raises(ConceptDomainError) as exc_info:
            Concept.validate_refines(["InvalidDomain.Concept"])
        assert "Domain must be snake_case" in str(exc_info.value)

    def test_validate_refines_invalid_concept(self):
        # Test refines with invalid concept format
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept.validate_refines(["valid_domain.invalid_concept"])
        assert "Code must be PascalCase" in str(exc_info.value)

    def test_validate_refines_multiple_dots(self):
        # Test refines with multiple dots
        with pytest.raises(ConceptError) as exc_info:
            Concept.validate_refines(["domain.concept.subconcept"])
        assert "Each refine code must contain a single dot" in str(exc_info.value)
