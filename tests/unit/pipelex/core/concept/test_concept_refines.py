import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.exceptions import ConceptCodeError, ConceptDomainError, ConceptError


class TestConceptRefinesValidationFunction:
    def test_validate_refines_success(self):
        # Test valid refines list
        valid_refines = ["domain1.Concept1", "domain2.Concept2", NativeConcept.TEXT.value]
        result = Concept.validate_refines(valid_refines)
        # NativeConcept.TEXT.value ("Text") should be converted to its full code "native.Text"
        expected = ["domain1.Concept1", "domain2.Concept2", NativeConcept.TEXT.code]
        assert result == expected

    def test_validate_refines_empty_list(self):
        # Test empty refines list
        result = Concept.validate_refines([])
        assert result == []

    def test_validate_refines_with_native_concept_strings(self):
        # Test refines with NativeConcept string values
        valid_refines = [
            "domain1.Concept1",
            NativeConcept.TEXT.value,
            NativeConcept.IMAGE.value,
            NativeConcept.PDF.value,
        ]
        result = Concept.validate_refines(valid_refines)
        # The NativeConcept strings should be converted to full codes
        expected = [
            "domain1.Concept1",
            NativeConcept.TEXT.code,
            NativeConcept.IMAGE.code,
            NativeConcept.PDF.code,
        ]
        assert result == expected

    def test_validate_refines_with_only_native_concepts(self):
        # Test refines with only NativeConcept values
        valid_refines = [
            NativeConcept.TEXT.value,
            NativeConcept.IMAGE.value,
            NativeConcept.DYNAMIC.value,
        ]
        result = Concept.validate_refines(valid_refines)
        expected = [
            NativeConcept.TEXT.code,
            NativeConcept.IMAGE.code,
            NativeConcept.DYNAMIC.code,
        ]
        assert result == expected

    def test_validate_refines_with_mixed_native_and_domain_concepts(self):
        # Test refines with mix of NativeConcept values and domain.concept codes
        valid_refines = [
            "my_domain.MyClass",
            NativeConcept.TEXT.value,
            "another_domain.AnotherClass",
            NativeConcept.IMAGE.value,
        ]
        result = Concept.validate_refines(valid_refines)
        expected = [
            "my_domain.MyClass",
            NativeConcept.TEXT.code,
            "another_domain.AnotherClass",
            NativeConcept.IMAGE.code,
        ]
        assert result == expected

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
