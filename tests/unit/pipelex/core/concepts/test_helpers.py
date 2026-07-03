import pytest

from pipelex.core.concepts.helpers import strip_markers_from_concept_ref_or_code


class TestStripMarkersFromConceptStringOrCode:
    """Test the strip_markers_from_concept_ref_or_code function."""

    @pytest.mark.parametrize(
        ("input_string", "expected_output"),
        [
            # No markers (PascalCase concepts)
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
            # Presence markers
            ("ConceptCode?", "ConceptCode"),
            ("ConceptCode!", "ConceptCode"),
            ("my_domain.ConceptCode?", "my_domain.ConceptCode"),
            ("my_domain.ConceptCode!", "my_domain.ConceptCode"),
            # Multiplicity and presence combined (multiplicity then presence)
            ("ConceptCode[]?", "ConceptCode"),
            ("ConceptCode[3]!", "ConceptCode"),
            ("my_domain.ConceptCode[]?", "my_domain.ConceptCode"),
        ],
    )
    def test_strip_markers(self, input_string: str, expected_output: str):
        """Test stripping multiplicity and presence markers from concept strings.

        This tests:
        - Concepts without markers (should return unchanged)
        - Concepts with empty multiplicity []
        - Concepts with numeric multiplicity [N]
        - Concepts with presence markers ? and !
        - Concepts with both multiplicity and presence markers
        """
        result = strip_markers_from_concept_ref_or_code(input_string)
        assert result == expected_output
