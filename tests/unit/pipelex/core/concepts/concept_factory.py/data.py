from typing import ClassVar, Optional, List, Tuple

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.core.concepts.concept_factory import DomainAndConceptCode
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain


class TestCases:
    # Test cases for make_refines method - only native concepts can be refined
    MAKE_REFINES_TEST_CASES: ClassVar[list[tuple[str, ConceptBlueprint, str]]] = [
        (
            "native_concept_string",
            ConceptBlueprint(definition="A concept that refines a native text concept", refines=NativeConceptEnum.TEXT),
            f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}",
        ),
        (
            "fully_qualified_native_string",
            ConceptBlueprint(
                definition="A concept that refines a fully qualified native concept",
                refines=f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}",
            ),
            f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}",
        ),
    ]

    # Test cases for make_domain_and_concept_code_from_concept_string_or_code method
    MAKE_DOMAIN_AND_CONCEPT_CODE_TEST_CASES: ClassVar[List[Tuple[str, str, List[str] | None, DomainAndConceptCode]]] = [
        # Test case 1: Concept string with dot notation
        ("my_domain", "other_domain.ConceptName", None, DomainAndConceptCode(domain="other_domain", concept_code="ConceptName")),
        # Test case 2: Concept string with dot notation (ignores same domain codes)
        ("my_domain", "other_domain.ConceptName", ["ConceptName"], DomainAndConceptCode(domain="other_domain", concept_code="ConceptName")),
        # Test case 3: Native concept code (Text)
        ("my_domain", "Text", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Text")),
        # Test case 4: Native concept code (Image)
        ("my_domain", "Image", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Image")),
        # Test case 5: Native concept code (PDF)
        ("my_domain", "PDF", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="PDF")),
        # Test case 6: Native concept code with same domain codes provided (native takes precedence)
        ("my_domain", "Text", ["Text", "OtherConcept"], DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Text")),
        # Test case 7: Concept code from same domain
        ("my_domain", "MyConcept", ["MyConcept", "OtherConcept"], DomainAndConceptCode(domain="my_domain", concept_code="MyConcept")),
        # Test case 8: Concept code from same domain (case sensitive)
        ("my_domain", "MyConcept", ["MyCon", "OtherConcept"], DomainAndConceptCode(domain=SpecialDomain.IMPLICIT, concept_code="MyConcept")),
        # Test case 9: Unknown concept code (no same domain codes)
        ("my_domain", "UnknownConcept", None, DomainAndConceptCode(domain=SpecialDomain.IMPLICIT, concept_code="UnknownConcept")),
        # Test case 10: Unknown concept code (not in same domain codes)
        (
            "my_domain",
            "UnknownConcept",
            ["KnownConcept", "OtherConcept"],
            DomainAndConceptCode(domain=SpecialDomain.IMPLICIT, concept_code="UnknownConcept"),
        ),
        # Test case 11: Empty same domain codes list
        ("my_domain", "SomeConcept", [], DomainAndConceptCode(domain=SpecialDomain.IMPLICIT, concept_code="SomeConcept")),
        # Test case 12: Different domain in concept string
        ("my_domain", "another_domain.SomeConcept", ["SomeConcept"], DomainAndConceptCode(domain="another_domain", concept_code="SomeConcept")),
        # Test case 13: All native concept codes
        ("my_domain", "Dynamic", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Dynamic")),
        ("my_domain", "TextAndImages", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="TextAndImages")),
        ("my_domain", "Number", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Number")),
        ("my_domain", "LlmPrompt", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="LlmPrompt")),
        ("my_domain", "Page", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Page")),
        ("my_domain", "Anything", None, DomainAndConceptCode(domain=SpecialDomain.NATIVE, concept_code="Anything")),
    ]

    # Test cases for make_from_blueprint method
    MAKE_FROM_BLUEPRINT_TEST_CASES: ClassVar[list[tuple[str, str, str, ConceptBlueprint, list[str] | None, Concept]]] = [
        # Test case 1: Simple blueprint with no structure or refines (goes to implicit)
        (
            "simple_blueprint",
            "my_domain",
            "SimpleConcept",
            ConceptBlueprint(definition="A simple concept"),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="SimpleConcept",
                definition="A simple concept",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines=None,
            ),
        ),
        # Test case 2: Blueprint with string structure (existing class, goes to implicit)
        (
            "string_structure_existing_class",
            "my_domain",
            "ConceptWithStructure",
            ConceptBlueprint(definition="A concept with string structure", structure="TextContent"),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="ConceptWithStructure",
                definition="A concept with string structure",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines=None,
            ),
        ),
        # Test case 3: Blueprint with refines (native concept, goes to implicit)
        (
            "blueprint_with_refines_text",
            "my_domain",
            "MyTextConcept",
            ConceptBlueprint(definition="A concept that refines Text", refines="Text"),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="MyTextConcept",
                definition="A concept that refines Text",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines="native.Text",
            ),
        ),
        # Test case 4: Blueprint with refines (fully qualified native concept, goes to implicit)
        (
            "blueprint_with_refines_native_image",
            "my_domain",
            "MyImageConcept",
            ConceptBlueprint(definition="A concept that refines native.Image", refines="native.Image"),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="MyImageConcept",
                definition="A concept that refines native.Image",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE].content_class_name,
                refines="native.Image",
            ),
        ),
        # Test case 5: Native concept code (should go to native domain)
        (
            "native_concept_code",
            "my_domain",
            "Text",
            ConceptBlueprint(definition="Native text concept"),
            None,
            Concept(
                domain=SpecialDomain.NATIVE,
                code="Text",
                definition="Native text concept",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines=None,
            ),
        ),
        # Test case 6: Concept code from same domain
        (
            "same_domain_concept",
            "my_domain",
            "DomainConcept",
            ConceptBlueprint(definition="A concept from same domain"),
            ["DomainConcept", "OtherConcept"],
            Concept(
                domain="my_domain",
                code="DomainConcept",
                definition="A concept from same domain",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines=None,
            ),
        ),
        # Test case 7: Unknown concept code (should go to implicit domain)
        (
            "implicit_concept",
            "my_domain",
            "UnknownConcept",
            ConceptBlueprint(definition="An unknown concept"),
            ["KnownConcept"],
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="UnknownConcept",
                definition="An unknown concept",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines=None,
            ),
        ),
        # Test case 8: Blueprint with dict structure (implicit domain)
        (
            "dict_structure_implicit",
            SpecialDomain.IMPLICIT,
            "PersonConcept",
            ConceptBlueprint(
                definition="A person with structured data",
                structure={
                    "name": "The person's name",
                    "age": ConceptStructureBlueprint(definition="The person's age", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
                    "active": ConceptStructureBlueprint(
                        definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
                    ),
                },
            ),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="PersonConcept",
                definition="A person with structured data",
                structure_class_name="PersonConcept",
                refines=None,
            ),
        ),
        # Test case 9: Blueprint with dict structure (same domain)
        (
            "dict_structure_same_domain",
            "my_domain",
            "PersonConcept",
            ConceptBlueprint(
                definition="A person with structured data",
                structure={
                    "name": ConceptStructureBlueprint(definition="The person's name", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                    "age": ConceptStructureBlueprint(definition="The person's age", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
                    "active": ConceptStructureBlueprint(
                        definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
                    ),
                },
            ),
            ["PersonConcept", "OtherConcept"],
            Concept(
                domain="my_domain",
                code="PersonConcept",
                definition="A person with structured data",
                structure_class_name="PersonConcept",
                refines=None,
            ),
        ),
        # Test case 10: Blueprint with refines (implicit domain)
        (
            "refines_implicit_domain",
            "my_domain",
            "ConceptWithRefines",
            ConceptBlueprint(definition="A concept with refines", refines="Text"),
            None,
            Concept(
                domain=SpecialDomain.IMPLICIT,
                code="ConceptWithRefines",
                definition="A concept with refines",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT].content_class_name,
                refines="native.Text",
            ),
        ),
        # Test case 11: Blueprint with refines (same domain)
        (
            "refines_same_domain",
            "my_domain",
            "ConceptWithRefines",
            ConceptBlueprint(definition="A concept with refines", refines="native.Image"),
            ["ConceptWithRefines", "OtherConcept"],
            Concept(
                domain="my_domain",
                code="ConceptWithRefines",
                definition="A concept with refines",
                structure_class_name=NATIVE_CONCEPTS_DATA[NativeConceptEnum.IMAGE].content_class_name,
                refines="native.Image",
            ),
        ),
    ]

    # Legacy alias for backward compatibility
    TEST_CASES = MAKE_REFINES_TEST_CASES
