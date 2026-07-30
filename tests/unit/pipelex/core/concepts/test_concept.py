import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.exceptions import NativeConceptDefinitionError
from pipelex.core.concepts.validation import validate_concept_ref
from pipelex.core.domains.domain import SpecialDomain


class TestConcept:
    """Test Concept class."""

    def test_get_validated_native_concept_ref(self):
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.TEXT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.IMAGE) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.DOCUMENT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.TEXT_AND_IMAGES)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.NUMBER) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.ANYTHING) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}"
        )
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.DYNAMIC) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DYNAMIC}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        )
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.TEXT}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.IMAGE}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.DOCUMENT}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.TEXT_AND_IMAGES}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.NUMBER}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.ANYTHING}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.DYNAMIC}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref("RandomConcept")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref("text")

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
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT,
                    domain_code=SpecialDomain.NATIVE,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.IMAGE,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.DOCUMENT,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT_AND_IMAGES,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.NUMBER,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.ANYTHING,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="RandomConcept",
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is False
        )

    def test_construct_concept_ref_with_domain(self):
        """Test construct_concept_ref_with_domain method."""
        valid_domain = "valid_domain"
        assert (
            ConceptFactory.make_concept_ref_with_domain(domain_code=valid_domain, concept_code=NativeConceptCode.TEXT)
            == f"{valid_domain}.{NativeConceptCode.TEXT}"
        )

    def test_validate_concept_ref(self):
        """Test validate_concept_ref method."""
        valid_domain = "valid_domain"
        valid_concept_code = "ConceptCode"
        valid_concept_ref = f"{valid_domain}.{valid_concept_code}"
        # Valid cases - should not raise exceptions
        validate_concept_ref(valid_concept_ref)
        validate_concept_ref(f"domain_123.{valid_concept_code}")
        validate_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}")
        validate_concept_ref(f"{valid_domain}.UPPERCASE")

        # Invalid cases - should raise ConceptCodeError
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"snake_case_domaiN.{valid_concept_code}")

        # Hierarchical domains (multiple dots) - now valid
        validate_concept_ref(f"domain.sub.{valid_concept_code}")
        validate_concept_ref(f"a.b.c.{valid_concept_code}")

        # Invalid domain (not snake_case)
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"InvalidDomain.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"domain-name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"Domain_Name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"123domain.{valid_concept_code}")

        # Invalid concept code (not PascalCase)
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.invalidText")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.text")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.Text_Name")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.text-name")

    @pytest.mark.parametrize(
        "domain_code",
        [
            "scoring_lib->scoring",
            "my_lib->legal.contracts",
        ],
    )
    def test_concept_with_cross_package_domain_code(self, domain_code: str):
        """Concept construction with a cross-package domain code should pass validation."""
        concept = Concept(
            code="WeightedScore",
            domain_code=domain_code,
            description="Test concept",
            structure_class_name="TextContent",
        )
        assert concept.domain_code == domain_code

    @pytest.mark.parametrize(
        "domain_code",
        [
            "lib->",
            "lib->Legal",
            "lib->.scoring",
        ],
    )
    def test_concept_with_invalid_cross_package_domain_code(self, domain_code: str):
        """Concept construction with an invalid cross-package domain code should raise."""
        with pytest.raises(ValidationError):
            Concept(
                code="WeightedScore",
                domain_code=domain_code,
                description="Test concept",
                structure_class_name="TextContent",
            )
