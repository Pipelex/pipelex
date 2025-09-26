import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum, NativeConceptManager
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.exceptions import DomainError


class TestConcept:
    """Test Concept class."""

    def test_is_native_concept_code(self):
        """Test is_native_concept_code method."""
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.TEXT) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.IMAGE) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.PDF) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.TEXT_AND_IMAGES) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.NUMBER) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.LLM_PROMPT) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.ANYTHING) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptEnum.DYNAMIC) is True

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.IMAGE}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.PDF}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT_AND_IMAGES}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.NUMBER}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.LLM_PROMPT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.TEXT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.IMAGE}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.PDF}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.TEXT_AND_IMAGES}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.NUMBER}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.LLM_PROMPT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptEnum.DYNAMIC}")

        assert ConceptBlueprint.is_native_concept_code("RandomConcept") is False
        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code("text")

    def test_is_native_concept_string_or_code(self):
        """Test is_native_concept_code method."""
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.TEXT) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.IMAGE) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.PDF) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.TEXT_AND_IMAGES) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.NUMBER) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.LLM_PROMPT) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.ANYTHING) is True
        assert NativeConceptManager.is_native_concept(NativeConceptEnum.DYNAMIC) is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}") is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.IMAGE}") is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.PDF}") is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT_AND_IMAGES}") is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.NUMBER}") is True
        assert NativeConceptManager.is_native_concept(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.LLM_PROMPT}") is True
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.TEXT}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.IMAGE}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.PDF}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.TEXT_AND_IMAGES}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.NUMBER}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.LLM_PROMPT}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.ANYTHING}") is False
        assert NativeConceptManager.is_native_concept(f"not_native.{NativeConceptEnum.DYNAMIC}") is False
        assert NativeConceptManager.is_native_concept("RandomConcept") is False
        assert NativeConceptManager.is_native_concept("text") is False

    def test_is_native_concept(self):
        """Test is_native_concept method."""
        valid_domain = "valid_domain"
        valid_definition = "Lorem Ipsum"

        for native_concept in NativeConceptEnum.values_list():
            assert Concept.is_native_concept(ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[native_concept])) is True

        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.TEXT,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.TEXT,
                    domain=SpecialDomain.NATIVE,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.IMAGE,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.PDF,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.TEXT_AND_IMAGES,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.NUMBER,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.LLM_PROMPT,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.ANYTHING,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="RandomConcept",
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is False
        )

    def test_construct_concept_string_with_domain(self):
        """Test construct_concept_string_with_domain method."""
        valid_domain = "valid_domain"
        assert (
            ConceptFactory.construct_concept_string_with_domain(domain=valid_domain, concept_code=NativeConceptEnum.TEXT)
            == f"{valid_domain}.{NativeConceptEnum.TEXT}"
        )

    def test_validate_concept_string(self):
        """Test validate_concept_string method."""
        valid_domain = "valid_domain"
        valid_concept_code = "ConceptCode"
        valid_concept_string = f"{valid_domain}.{valid_concept_code}"
        # Valid cases - should not raise exceptions
        assert ConceptBlueprint.validate_concept_string(valid_concept_string) is None
        assert ConceptBlueprint.validate_concept_string(f"snake_case_domain.{valid_concept_code}") is None
        assert ConceptBlueprint.validate_concept_string(f"domain_123.{valid_concept_code}") is None
        assert ConceptBlueprint.validate_concept_string(f"{valid_domain}.TEXT") is None
        assert ConceptBlueprint.validate_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptEnum.ANYTHING}") is None

        # Invalid cases - should raise ConceptCodeError

        # Multiple dots
        with pytest.raises(ConceptStringError):
            ConceptBlueprint.validate_concept_string(f"domain.sub.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            ConceptBlueprint.validate_concept_string(f"a.b.c.{valid_concept_code}")

        # Invalid domain (not snake_case)
        with pytest.raises(DomainError):
            ConceptBlueprint.validate_concept_string(f"InvalidDomain.{valid_concept_code}")

        with pytest.raises(DomainError):
            ConceptBlueprint.validate_concept_string(f"domain-name.{valid_concept_code}")

        with pytest.raises(DomainError):
            ConceptBlueprint.validate_concept_string(f"Domain_Name.{valid_concept_code}")

        with pytest.raises(DomainError):
            ConceptBlueprint.validate_concept_string(f"123domain.{valid_concept_code}")

        # Invalid concept code (not PascalCase)
        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.validate_concept_string(f"{valid_domain}.invalidText")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.validate_concept_string(f"{valid_domain}.text")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.validate_concept_string(f"{valid_domain}.Text_Name")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.validate_concept_string(f"{valid_domain}.text-name")

        # Invalid native concept
        with pytest.raises(ConceptStringError):
            ConceptBlueprint.validate_concept_string(f"{SpecialDomain.NATIVE}.InvalidNativeConcept")

    def test_are_concept_compatible(self):
        concept1 = ConceptFactory.make_from_blueprint(
            concept_code="Code1",
            domain="domain1",
            blueprint=ConceptBlueprint(definition="Lorem Ipsum", refines=NativeConceptEnum.TEXT),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept2 = ConceptFactory.make_from_blueprint(
            concept_code="Code2",
            domain="domain1",
            blueprint=ConceptBlueprint(definition="Lorem Ipsum", refines=NativeConceptEnum.TEXT),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept3 = ConceptFactory.make_from_blueprint(
            concept_code="Code3",
            domain="domain2",
            blueprint=ConceptBlueprint(definition="Lorem Ipsum", structure="TextContent"),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept4 = ConceptFactory.make_from_blueprint(
            concept_code="Code4",
            domain="domain1",
            blueprint=ConceptBlueprint(definition="Lorem Ipsum", structure="ImageContent"),
            concept_codes_from_the_same_domain=["Code1"],
        )

        concept_5 = ConceptFactory.make_native_concept(
            native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.PAGE],
        )

        concept_6 = ConceptFactory.make_native_concept(
            native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE],
        )

        concept_7 = ConceptFactory.make_from_blueprint(
            concept_code="VisualDescription",
            domain="images",
            blueprint=ConceptBlueprint(definition="Lorem Ipsum"),
        )

        assert Concept.are_concept_compatible(concept_7, concept_6, strict=True) is False
        assert Concept.are_concept_compatible(concept_7, concept_6, strict=False) is False

        # Test same code and domain
        assert Concept.are_concept_compatible(concept1, concept2) is True

        # Test different code and domain
        assert Concept.are_concept_compatible(concept1, concept3) is True

        # Test same structure class name
        assert Concept.are_concept_compatible(concept1, concept4) is False

        # Test same refines
        assert Concept.are_concept_compatible(concept_5, concept_6, strict=False) is True
        assert Concept.are_concept_compatible(concept_5, concept_6, strict=True) is False
