import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_string
from pipelex.core.domains.domain import SpecialDomain


class TestConcept:
    """Test Concept class."""

    def test_get_validated_native_concept_string(self):
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.TEXT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.IMAGE) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.PDF) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.PDF}"
        assert (
            NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.TEXT_AND_IMAGES)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert NativeConceptCode.get_validated_native_concept_string(NativeConceptCode.NUMBER) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
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
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.TEXT}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.IMAGE}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.PDF}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.TEXT_AND_IMAGES}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.NUMBER}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.ANYTHING}") is None
        assert NativeConceptCode.get_validated_native_concept_string(f"not_native.{NativeConceptCode.DYNAMIC}") is None
        assert NativeConceptCode.get_validated_native_concept_string("RandomConcept") is None
        assert NativeConceptCode.get_validated_native_concept_string("text") is None

    def test_is_native_concept(self):
        """Test is_native_concept method."""
        valid_domain = "valid_domain"
        valid_definition = "Lorem Ipsum"

        for native_concept_code in NativeConceptCode.values_list():
            native_concept = ConceptFactory.make_native_concept(native_concept_code=native_concept_code)
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
        validate_concept_string(valid_concept_string)
        validate_concept_string(f"domain_123.{valid_concept_code}")
        validate_concept_string(f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}")
        validate_concept_string(f"{valid_domain}.UPPERCASE")

        # Invalid cases - should raise ConceptCodeError
        with pytest.raises(ConceptStringError):
            validate_concept_string(f"snake_case_domaiN.{valid_concept_code}")

        # Multiple dots
        with pytest.raises(ConceptStringError):
            validate_concept_string(f"domain.sub.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"a.b.c.{valid_concept_code}")

        # Invalid domain (not snake_case)
        with pytest.raises(ConceptStringError):
            validate_concept_string(f"InvalidDomain.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"domain-name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"Domain_Name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"123domain.{valid_concept_code}")

        # Invalid concept code (not PascalCase)
        with pytest.raises(ConceptStringError):
            validate_concept_string(f"{valid_domain}.invalidText")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"{valid_domain}.text")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"{valid_domain}.Text_Name")

        with pytest.raises(ConceptStringError):
            validate_concept_string(f"{valid_domain}.text-name")

        # Invalid native concept
        with pytest.raises(ConceptStringError):
            validate_concept_string(f"{SpecialDomain.NATIVE}.InvalidNativeConcept")

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

        concept_5 = ConceptFactory.make_native_concept(
            native_concept_code=NativeConceptCode.PAGE,
        )

        concept_6 = ConceptFactory.make_native_concept(
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

    def test_concept_refining_text_is_strictly_compatible(self):
        """Test that a concept created with .make() that refines native.Text is strictly compatible with Text."""
        # Create a concept that refines native.Text using ConceptFactory.make()
        concept_not_native_text = ConceptFactory.make(
            domain="test_domain",
            concept_code="MyConceptNotNativeText",
            description="Test concept for unit tests",
            structure_class_name="TextContent",
            refines="native.Text",
        )

        # Get the native Text concept
        text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

        # A concept that refines Text should be strictly compatible with Text
        assert Concept.are_concept_compatible(concept_not_native_text, text_concept, strict=True) is True
        assert Concept.are_concept_compatible(concept_not_native_text, text_concept, strict=False) is True
