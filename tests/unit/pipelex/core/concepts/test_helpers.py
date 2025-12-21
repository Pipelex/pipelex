import pytest

from pipelex.core.concepts.helpers import strip_multiplicity_from_concept_ref_or_code


class TestStripMultiplicityFromConceptStringOrCode:
    """Test the strip_multiplicity_from_concept_ref_or_code function."""

    @pytest.mark.parametrize(
        ("input_string", "expected_output"),
        [
            # No multiplicity (PascalCase concepts)
            ("ConceptCode", "ConceptCode"),
            ("MyConceptCode", "MyConceptCode"),
            ("ComplexConceptName", "ComplexConceptName"),
            # Empty multiplicity
            ("ConceptCode[]", "ConceptCode"),
            ("MyConceptCode[]", "MyConceptCode"),
            # Single digit multiplicity
            ("ConceptCode[1]", "ConceptCode"),
            ("ConceptCode[5]", "ConceptCode"),
            ("ConceptCode[9]", "ConceptCode"),
            # Multi-digit multiplicity
            ("ConceptCode[10]", "ConceptCode"),
            ("ConceptCode[100]", "ConceptCode"),
            ("ConceptCode[999]", "ConceptCode"),
            # Large number multiplicity
            ("ConceptCode[1000]", "ConceptCode"),
            ("ConceptCode[99999]", "ConceptCode"),
            ("ConceptCode[999999]", "ConceptCode"),
            # More PascalCase concepts with multiplicity
            ("MyConcept[123]", "MyConcept"),
            ("AnotherConcept[42]", "AnotherConcept"),
            # Domain-prefixed concepts (domain.ConceptCode format)
            # Domain is snake_case, Concept is PascalCase
            ("my_domain.ConceptCode", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode[]", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode[1]", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode[5]", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode[100]", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode[9999]", "my_domain.ConceptCode"),
            # Different domain names with multiplicity
            ("some_domain.MyConceptCode[42]", "some_domain.MyConceptCode"),
            ("another_domain.SomeOtherConcept[]", "another_domain.SomeOtherConcept"),
            ("complex_domain_name.ComplexConceptName[123]", "complex_domain_name.ComplexConceptName"),
        ],
    )
    def test_strip_multiplicity(self, input_string: str, expected_output: str):
        """Test stripping multiplicity from concept strings with various formats.

        This tests:
        - Concepts without multiplicity (should return unchanged)
        - Concepts with empty multiplicity []
        - Concepts with single-digit multiplicity [1-9]
        - Concepts with multi-digit multiplicity [10-999]
        - Concepts with large multiplicity [1000+]
        """
        result = strip_multiplicity_from_concept_ref_or_code(input_string)
        assert result == expected_output
