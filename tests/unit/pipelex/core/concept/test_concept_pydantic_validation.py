import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.exceptions import ConceptCodeError, ConceptDomainError


class TestConceptPydanticFieldValidation:
    """Test Concept validation through Pydantic field validation by instantiating the class."""

    def test_concept_creation_with_valid_refines(self):
        """Test successful concept creation with valid refines list."""
        concept = Concept(
            code="test_domain.TestConcept",
            domain="test_domain",
            structure_class_name="TextContent",
            definition="A test concept",
            refines=["domain1.Concept1", "domain2.Concept2"],
        )
        assert concept.refines == ["domain1.Concept1", "domain2.Concept2"]

    def test_concept_creation_with_empty_refines(self):
        """Test successful concept creation with empty refines list."""
        concept = Concept(
            code="test_domain.TestConcept", domain="test_domain", structure_class_name="TextContent", definition="A test concept", refines=[]
        )
        assert concept.refines == []

    def test_concept_creation_with_default_refines(self):
        """Test successful concept creation without specifying refines (should default to empty list)."""
        concept = Concept(code="test_domain.TestConcept", domain="test_domain", structure_class_name="TextContent", definition="A test concept")
        assert concept.refines == []

    def test_concept_creation_with_native_concept_refines(self):
        """Test successful concept creation with NativeConcept string values in refines."""
        concept = Concept(
            code="test_domain.TestConcept",
            domain="test_domain",
            structure_class_name="TextContent",
            definition="A test concept",
            refines=[
                NativeConcept.TEXT.value,
                NativeConcept.IMAGE.value,
                NativeConcept.PDF.value,
            ],
        )
        # NativeConcept strings should be converted to full codes
        assert concept.refines == [
            NativeConcept.TEXT.code,
            NativeConcept.IMAGE.code,
            NativeConcept.PDF.code,
        ]

    def test_concept_creation_with_mixed_refines(self):
        """Test successful concept creation with mix of NativeConcept and domain.concept refines."""
        concept = Concept(
            code="test_domain.TestConcept",
            domain="test_domain",
            structure_class_name="TextContent",
            definition="A test concept",
            refines=[
                "valid_domain.ValidConcept",
                NativeConcept.TEXT.value,
                "another_domain.AnotherConcept",
                NativeConcept.IMAGE.value,
            ],
        )
        expected_refines = [
            "valid_domain.ValidConcept",
            NativeConcept.TEXT.code,
            "another_domain.AnotherConcept",
            NativeConcept.IMAGE.code,
        ]
        assert concept.refines == expected_refines

    def test_concept_creation_with_only_native_concept_refines(self):
        """Test successful concept creation with only NativeConcept values in refines."""
        concept = Concept(
            code="test_domain.TestConcept",
            domain="test_domain",
            structure_class_name="TextContent",
            definition="A test concept",
            refines=[
                NativeConcept.DYNAMIC.value,
                NativeConcept.TEXT.value,
                NativeConcept.NUMBER.value,
            ],
        )
        assert concept.refines == [
            NativeConcept.DYNAMIC.code,
            NativeConcept.TEXT.code,
            NativeConcept.NUMBER.code,
        ]

    def test_concept_creation_with_refines_missing_dot(self):
        """Test concept creation fails when refines contain invalid codes missing dot."""
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=["invalidConcept"],
            )

        assert "Each refine code must contain a single dot" in str(exc_info.value)

    def test_concept_creation_with_refines_invalid_domain(self):
        """Test concept creation fails when refines contain invalid domain format."""
        with pytest.raises(ConceptDomainError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=["InvalidDomain.Concept"],
            )

        assert "Domain must be snake_case" in str(exc_info.value)

    def test_concept_creation_with_refines_invalid_concept_code(self):
        """Test concept creation fails when refines contain invalid concept code format."""
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=["valid_domain.invalid_concept"],
            )

        assert "Code must be PascalCase" in str(exc_info.value)

    def test_concept_creation_with_multiple_refines_errors(self):
        """Test concept creation fails when multiple refines are invalid."""
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=[
                    "invalidConcept",
                    "InvalidDomain.Concept",
                    "valid_domain.invalid_concept",
                ],
            )

        # The first error should be about the missing dot (validation stops at first error)
        assert "Each refine code must contain a single dot" in str(exc_info.value)

    def test_concept_creation_with_mixed_valid_invalid_refines(self):
        """Test concept creation fails even when some refines are valid but others are invalid."""
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=[
                    "valid_domain.ValidConcept",
                    "invalidConcept",
                ],
            )

        assert "Each refine code must contain a single dot" in str(exc_info.value)

    def test_concept_creation_with_refines_multiple_dots(self):
        """Test concept creation fails when refines contain codes with multiple dots."""
        with pytest.raises(ConceptCodeError) as exc_info:
            Concept(
                code="test_domain.TestConcept",
                domain="test_domain",
                structure_class_name="TextContent",
                definition="A test concept",
                refines=["domain.concept.subconcept"],
            )

        assert "Each refine code must contain a single dot" in str(exc_info.value)

    def test_concept_creation_with_valid_complex_refines(self):
        """Test successful concept creation with more complex valid refines."""
        concept = Concept(
            code="my_domain.MyTestConcept",
            domain="my_domain",
            structure_class_name="TextContent",
            definition="A complex test concept",
            refines=[
                "base_domain.BaseConcept",
                "another_domain.AnotherConcept123",
                "third_domain.ThirdConcept",
                "snake_case_domain.PascalCaseConcept",
            ],
        )
        assert len(concept.refines) == 4
        assert "base_domain.BaseConcept" in concept.refines
        assert "snake_case_domain.PascalCaseConcept" in concept.refines
