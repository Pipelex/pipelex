import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.exceptions import DomainError


class TestConcept:
    """Test Concept class."""

    def test_is_native_concept_code(self):
        """Test is_native_concept_code method."""
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.TEXT) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.IMAGE) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.PDF) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.TEXT_AND_IMAGES) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.NUMBER) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.LLM_PROMPT) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.ANYTHING) is True
        assert ConceptBlueprint.is_native_concept_code(NativeConceptCode.DYNAMIC) is True

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.PDF}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"{SpecialDomain.NATIVE}.{NativeConceptCode.LLM_PROMPT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.TEXT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.IMAGE}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.PDF}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.TEXT_AND_IMAGES}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.NUMBER}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.LLM_PROMPT}")

        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code(f"not_native.{NativeConceptCode.DYNAMIC}")

        assert ConceptBlueprint.is_native_concept_code("RandomConcept") is False
        with pytest.raises(ConceptCodeError):
            ConceptBlueprint.is_native_concept_code("text")

    def test_get_validated_native_concept_string(self):
        """Test is_native_concept_code method."""
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.TEXT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.IMAGE) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.PDF) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.PDF}"
        assert (
            NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.TEXT_AND_IMAGES)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.NUMBER) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        assert (
            NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.LLM_PROMPT)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.LLM_PROMPT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.ANYTHING)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.DYNAMIC) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DYNAMIC}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.PDF}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.PDF}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.LLM_PROMPT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.LLM_PROMPT}"
        )
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.TEXT}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.IMAGE}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.PDF}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.TEXT_AND_IMAGES}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.NUMBER}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.LLM_PROMPT}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.ANYTHING}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.DYNAMIC}") is None
        assert NativeConceptCode.get_validated_native_concept_string("RandomConcept") is None
        assert NativeConceptCode.get_validated_native_concept_string("text") is None

    def test_is_native_concept(self):
        """Test is_native_concept method."""
        valid_domain = "valid_domain"
        valid_definition = "Lorem Ipsum"

        for native_concept_code in NativeConceptCode.values_list():
            native_concept = ConceptFactory.make_native_concept_from_enum(native_concept_code=native_concept_code)
            assert Concept.is_native_concept(native_concept) is True

        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT,
                    domain=SpecialDomain.NATIVE,
                    blueprint=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.IMAGE,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.PDF,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT_AND_IMAGES,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.NUMBER,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.LLM_PROMPT,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.ANYTHING,
                    domain=valid_domain,
                    blueprint=ConceptBlueprint(description=valid_definition),
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
                    blueprint=ConceptBlueprint(description=valid_definition),
                    concept_codes_from_the_same_domain=["RandomConcept"],
                ),
            )
            is False
        )

    def test_construct_concept_string_with_domain(self):
        """Test construct_concept_string_with_domain method."""
        valid_domain = "valid_domain"
        assert (
            ConceptFactory.make_concept_string_with_domain(domain=valid_domain, concept_code=NativeConceptCode.TEXT)
            == f"{valid_domain}.{NativeConceptCode.TEXT}"
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
        assert ConceptBlueprint.validate_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}") is None

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
            blueprint=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept2 = ConceptFactory.make_from_blueprint(
            concept_code="Code2",
            domain="domain1",
            blueprint=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept3 = ConceptFactory.make_from_blueprint(
            concept_code="Code3",
            domain="domain2",
            blueprint=ConceptBlueprint(description="Lorem Ipsum", structure="TextContent"),
            concept_codes_from_the_same_domain=["Code1"],
        )
        concept4 = ConceptFactory.make_from_blueprint(
            concept_code="Code4",
            domain="domain1",
            blueprint=ConceptBlueprint(description="Lorem Ipsum", structure="ImageContent"),
            concept_codes_from_the_same_domain=["Code1"],
        )

        concept_5 = ConceptFactory.make_native_concept_from_enum(
            native_concept_code=NativeConceptCode.PAGE,
        )

        concept_6 = ConceptFactory.make_native_concept_from_enum(
            native_concept_code=NativeConceptCode.IMAGE,
        )

        concept_7 = ConceptFactory.make_from_blueprint(
            concept_code="VisualDescription",
            domain="images",
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
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
