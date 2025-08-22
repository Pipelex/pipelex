import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptDomainError, ConceptStringError
from pipelex.core.domains.domain import SpecialDomain


class TestConcept:
    """Test Concept class."""

    def test_is_native_concept_code(self):
        """Test is_native_concept_code method."""
        assert Concept.is_native_concept_code(NativeConceptEnum.TEXT.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.IMAGE.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.PDF.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.TEXT_AND_IMAGES.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.NUMBER.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.LLM_PROMPT.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.ANYTHING.value) is True
        assert Concept.is_native_concept_code(NativeConceptEnum.DYNAMIC.value) is True
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}") is False
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.IMAGE.value}") is False
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.PDF.value}") is False
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT_AND_IMAGES.value}") is False
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.NUMBER.value}") is False
        assert Concept.is_native_concept_code(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.LLM_PROMPT.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.TEXT.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.IMAGE.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.PDF.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.TEXT_AND_IMAGES.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.NUMBER.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.LLM_PROMPT.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.ANYTHING.value}") is False
        assert Concept.is_native_concept_code(f"not_native.{NativeConceptEnum.DYNAMIC.value}") is False
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
                    concept_code=NativeConceptEnum.TEXT.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.TEXT.value,
                    domain=SpecialDomain.NATIVE.value,
                    blueprint=ConceptBlueprint(definition=valid_definition),
                )
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.IMAGE.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.PDF.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.TEXT_AND_IMAGES.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.NUMBER.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.LLM_PROMPT.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptEnum.ANYTHING.value, domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="RandomConcept", domain=valid_domain, blueprint=ConceptBlueprint(definition=valid_definition)
                )
            )
            is False
        )

    def test_construct_concept_string_with_domain(self):
        """Test construct_concept_string_with_domain method."""
        valid_domain = "valid_domain"
        assert (
            Concept.construct_concept_string_with_domain(domain=valid_domain, concept_code=NativeConceptEnum.TEXT.value)
            == f"{valid_domain}.{NativeConceptEnum.TEXT.value}"
        )

    def test_validate_concept_string(self):
        """Test validate_concept_string method."""
        valid_domain = "valid_domain"
        valid_concept_code = NativeConceptEnum.TEXT.value
        valid_concept_string = f"{valid_domain}.{valid_concept_code}"
        # Valid cases - should not raise exceptions
        assert Concept.validate_concept_string(valid_concept_string) is None
        assert Concept.validate_concept_string(f"snake_case_domain.{valid_concept_code}") is None
        assert Concept.validate_concept_string(f"domain_123.{valid_concept_code}") is None
        assert Concept.validate_concept_string(f"{valid_domain}.TEXT") is None
        assert Concept.validate_concept_string(f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.ANYTHING.value}") is None

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
            Concept.validate_concept_string(f"{SpecialDomain.NATIVE.value}.InvalidNativeConcept")
