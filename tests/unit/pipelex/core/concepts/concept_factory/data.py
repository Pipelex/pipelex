from typing import ClassVar

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
)
from pipelex.core.concepts.concept_factory import DomainAndConceptCode
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain


class TestCases:
    # Test cases for make_refines method
    # Format: (test_name, domain_code, blueprint, expected_result)
    MAKE_REFINES_TEST_CASES: ClassVar[list[tuple[str, str, ConceptBlueprint, str]]] = [
        (
            "native_concept_ref",
            "test_domain",
            ConceptBlueprint(description="A concept that refines a native text concept", refines=NativeConceptCode.TEXT),
            f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        ),
        (
            "fully_qualified_native_string",
            "test_domain",
            ConceptBlueprint(
                description="A concept that refines a fully qualified native concept",
                refines=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
            ),
            f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        ),
        (
            "native_without_domain",
            "test_domain",
            ConceptBlueprint(description="A concept that refines a native concept without domain", refines=NativeConceptCode.TEXT),
            f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        ),
        (
            "local_concept_without_domain",
            "my_domain",
            ConceptBlueprint(description="A concept that refines a local concept", refines="LocalConcept"),
            "my_domain.LocalConcept",
        ),
        (
            "external_concept_with_domain",
            "my_domain",
            ConceptBlueprint(description="A concept that refines an external concept", refines="other_domain.ExternalConcept"),
            "other_domain.ExternalConcept",
        ),
    ]

    # Test cases for make_domain_and_concept_code_from_concept_ref_or_concept_code method
    MAKE_DOMAIN_AND_CONCEPT_CODE_TEST_CASES: ClassVar[list[tuple[str, str, DomainAndConceptCode]]] = [
        # Test case 1: Concept string with dot notation
        ("my_domain", "other_domain.ConceptName", DomainAndConceptCode(domain_code="other_domain", concept_code="ConceptName")),
        # Test case 2: Concept string with dot notation (ignores same domain codes)
        ("my_domain", "other_domain.ConceptName", DomainAndConceptCode(domain_code="other_domain", concept_code="ConceptName")),
        # Test case 3: Native concept code (Text)
        ("my_domain", "Text", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Text")),
        # Test case 4: Native concept code (Image)
        ("my_domain", "Image", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Image")),
        # Test case 5: Native concept code (Document)
        ("my_domain", "Document", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Document")),
        # Test case 6: Native concept code with same domain codes provided (native takes precedence)
        ("my_domain", "Text", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Text")),
        # Test case 7: Concept code from same domain
        ("my_domain", "MyConcept", DomainAndConceptCode(domain_code="my_domain", concept_code="MyConcept")),
        # Test case 8: Different domain in concept string
        ("my_domain", "another_domain.SomeConcept", DomainAndConceptCode(domain_code="another_domain", concept_code="SomeConcept")),
        # Test case 13: All native concept codes
        ("my_domain", "Dynamic", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Dynamic")),
        ("my_domain", "TextAndImages", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="TextAndImages")),
        ("my_domain", "Number", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Number")),
        ("my_domain", "Page", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Page")),
        ("my_domain", "Anything", DomainAndConceptCode(domain_code=SpecialDomain.NATIVE, concept_code="Anything")),
    ]

    # Test cases for make_from_blueprint method
    MAKE_FROM_BLUEPRINT_TEST_CASES: ClassVar[list[tuple[str, str, str, ConceptBlueprint, Concept]]] = [
        # Test case 5: Native concept code (should go to native domain)
        (
            "native_concept_code",
            "my_domain",
            "Text",
            ConceptBlueprint(description="Native text concept"),
            Concept(
                domain_code=SpecialDomain.NATIVE,
                code="Text",
                description="Native text concept",
                structure_class_name=NativeConceptCode.TEXT.structure_class_name,
                refines=NativeConceptCode.TEXT.concept_ref,
            ),
        ),
        # Test case 6: Concept code from same domain
        (
            "same_domain_concept",
            "my_domain",
            "DomainConcept",
            ConceptBlueprint(description="A concept from same domain"),
            Concept(
                domain_code="my_domain",
                code="DomainConcept",
                description="A concept from same domain",
                structure_class_name="my_domain__DomainConcept",
                refines="native.Text",
            ),
        ),
        # Test case 9: Blueprint with dict structure (same domain)
        (
            "dict_structure_same_domain",
            "my_domain",
            "PersonConcept",
            ConceptBlueprint(
                description="A person with structured data",
                structure={
                    "name": ConceptStructureBlueprint(description="The person's name", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                    "age": ConceptStructureBlueprint(description="The person's age", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
                    "active": ConceptStructureBlueprint(
                        description="Whether the person is active",
                        type=ConceptStructureBlueprintFieldType.BOOLEAN,
                        required=False,
                        default_value=True,
                    ),
                },
            ),
            Concept(
                domain_code="my_domain",
                code="PersonConcept",
                description="A person with structured data",
                structure_class_name="my_domain__PersonConcept",
                refines=None,
            ),
        ),
        # Test case 11: Blueprint with refines (same domain)
        (
            "refines_same_domain",
            "my_domain",
            "ConceptWithRefines",
            ConceptBlueprint(description="A concept with refines", refines="native.Image"),
            Concept(
                domain_code="my_domain",
                code="ConceptWithRefines",
                description="A concept with refines",
                structure_class_name="my_domain__ConceptWithRefines",
                refines="native.Image",
            ),
        ),
    ]

    # Legacy alias for backward compatibility
    TEST_CASES = MAKE_REFINES_TEST_CASES
