import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptDomainError, ConceptStringError


class TestConcept:
    """Test Concept class."""

    def test_is_native_concept_code(self):
        """Test is_native_concept_code method."""
        assert Concept.is_native_concept_code("Text") is True
        assert Concept.is_native_concept_code("Image") is True
        assert Concept.is_native_concept_code("PDF") is True
        assert Concept.is_native_concept_code("TextAndImages") is True
        assert Concept.is_native_concept_code("Number") is True
        assert Concept.is_native_concept_code("LlmPrompt") is True
        assert Concept.is_native_concept_code("Anything") is True
        assert Concept.is_native_concept_code("Dynamic") is True
        assert Concept.is_native_concept_code("native.Text") is False
        assert Concept.is_native_concept_code("native.Image") is False
        assert Concept.is_native_concept_code("native.PDF") is False
        assert Concept.is_native_concept_code("native.TextAndImages") is False
        assert Concept.is_native_concept_code("native.Number") is False
        assert Concept.is_native_concept_code("native.LlmPrompt") is False
        assert Concept.is_native_concept_code("not_native.Text") is False
        assert Concept.is_native_concept_code("not_native.Image") is False
        assert Concept.is_native_concept_code("not_native.PDF") is False
        assert Concept.is_native_concept_code("not_native.TextAndImages") is False
        assert Concept.is_native_concept_code("not_native.Number") is False
        assert Concept.is_native_concept_code("not_native.LlmPrompt") is False
        assert Concept.is_native_concept_code("not_native.Anything") is False
        assert Concept.is_native_concept_code("not_native.Dynamic") is False
        assert Concept.is_native_concept_code("RandomConcept") is False
        assert Concept.is_native_concept_code("text") is False

    def test_is_native_concept(self):
        """Test is_native_concept method."""
        valid_domain = "valid_domain"
        valid_definition = "Lorem Ipsum"

        for native_concept in NativeConceptEnum:
            assert Concept.is_native_concept(ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[native_concept])) is True

        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="Text", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="Text", domain="native", concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="Image", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="PDF", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="TextAndImages", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="Number", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="LlmPrompt", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="Anything", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="RandomConcept", domain=valid_domain, concept_blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )

    def test_construct_concept_string_with_domain(self):
        """Test construct_concept_string_with_domain method."""
        valid_domain = "valid_domain"
        assert Concept.construct_concept_string_with_domain(domain=valid_domain, concept_code="Text") == f"{valid_domain}.Text"

    def test_validate_concept_string(self):
        """Test validate_concept_string method."""
        valid_domain = "valid_domain"
        valid_concept_code = "Text"
        valid_concept_string = f"{valid_domain}.{valid_concept_code}"
        # Valid cases - should not raise exceptions
        assert Concept.validate_concept_string(valid_concept_string) is None
        assert Concept.validate_concept_string(f"snake_case_domain.{valid_concept_code}") is None
        assert Concept.validate_concept_string(f"domain_123.{valid_concept_code}") is None
        assert Concept.validate_concept_string(f"{valid_domain}.TEXT") is None
        assert Concept.validate_concept_string("native.Anything") is None

        # Invalid cases - should raise ConceptCodeError

        # Multiple dots
        with pytest.raises(ConceptStringError):
            Concept.validate_concept_string(f"domain.sub.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            Concept.validate_concept_string(f"a.b.c.{valid_concept_code}")

        # Invalid domain (not snake_case)
        with pytest.raises(ConceptDomainError):
            Concept.validate_concept_string(f"InvalidDomain.{valid_concept_code}")

        with pytest.raises(ConceptDomainError):
            Concept.validate_concept_string(f"domain-name.{valid_concept_code}")

        with pytest.raises(ConceptDomainError):
            Concept.validate_concept_string(f"Domain_Name.{valid_concept_code}")

        with pytest.raises(ConceptDomainError):
            Concept.validate_concept_string(f"123domain.{valid_concept_code}")

        # Invalid concept code (not PascalCase)
        with pytest.raises(ConceptCodeError):
            Concept.validate_concept_string(f"{valid_domain}.invalidText")

        with pytest.raises(ConceptCodeError):
            Concept.validate_concept_string(f"{valid_domain}.text")

        with pytest.raises(ConceptCodeError):
            Concept.validate_concept_string(f"{valid_domain}.Text_Name")

        with pytest.raises(ConceptCodeError):
            Concept.validate_concept_string(f"{valid_domain}.text-name")

        # Invalid native concept
        with pytest.raises(ConceptCodeError):
            Concept.validate_concept_string("native.InvalidNativeConcept")

    def test_are_concept_compatible_same_refines_different_order(self):
        """Test that concepts with same refines in different order are compatible."""
        concept1 = Concept(
            code="TestConcept1",
            domain="test_domain",
            definition="Test concept 1",
            structure_class_name="TestClass1",
            refines=["native.Text", "native.Image", "native.PDF"],
        )

        concept2 = Concept(
            code="TestConcept2",
            domain="test_domain",
            definition="Test concept 2",
            structure_class_name="TestClass2",
            refines=["native.PDF", "native.Text", "native.Image"],  # Different order
        )

        assert Concept.are_concept_compatible(concept1, concept2) is True

    def test_are_concept_compatible_different_refines(self):
        """Test that concepts with different refines are not compatible."""
        concept1 = Concept(
            code="TestConcept1",
            domain="test_domain",
            definition="Test concept 1",
            structure_class_name="TestClass1",
            refines=["native.Text", "native.Image"],
        )

        concept2 = Concept(
            code="TestConcept2",
            domain="test_domain",
            definition="Test concept 2",
            structure_class_name="TestClass2",
            refines=["native.Text", "native.PDF"],  # Different elements
        )

        assert Concept.are_concept_compatible(concept1, concept2) is False

    def test_are_concept_compatible_empty_refines(self):
        """Test compatibility with empty refines arrays."""
        concept1 = Concept(code="TestConcept1", domain="test_domain", definition="Test concept 1", structure_class_name="TestClass1", refines=[])

        concept2 = Concept(code="TestConcept2", domain="test_domain", definition="Test concept 2", structure_class_name="TestClass2", refines=[])

        assert Concept.are_concept_compatible(concept1, concept2) is True

    def test_are_concept_compatible_one_empty_refines(self):
        """Test compatibility when one has empty refines and other doesn't."""
        concept1 = Concept(code="TestConcept1", domain="test_domain", definition="Test concept 1", structure_class_name="TestClass1", refines=[])

        concept2 = Concept(
            code="TestConcept2", domain="test_domain", definition="Test concept 2", structure_class_name="TestClass2", refines=["native.Text"]
        )

        assert Concept.are_concept_compatible(concept1, concept2) is False
