"""Test data for ConceptFactory._make_refines tests."""

from typing import ClassVar, List, Tuple

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain


class TestCases:
    """Test cases for ConceptFactory._make_refines method."""

    # Test cases with expected results
    TEST_CASES: ClassVar[List[Tuple[str, ConceptBlueprint, List[str]]]] = [
        (
            "native_concept_string",
            ConceptBlueprint(definition="A concept that refines a native text concept", refines=NativeConceptEnum.TEXT.value),
            [f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}"],
        ),
        (
            "domain_concept_string",
            ConceptBlueprint(definition="A concept that refines a domain concept", refines="CustomConcept"),
            ["test_domain.CustomConcept"],
        ),
        (
            "fully_qualified_string",
            ConceptBlueprint(definition="A concept that refines a fully qualified concept", refines="some_domain.SomeConcept"),
            ["some_domain.SomeConcept"],
        ),
        (
            "mixed_list",
            ConceptBlueprint(
                definition="A concept that refines multiple concepts",
                refines=[NativeConceptEnum.TEXT.value, "CustomConcept", "other_domain.OtherConcept"],
            ),
            [f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}", "test_domain.CustomConcept", "other_domain.OtherConcept"],
        ),
        (
            "mixed_list_with_full_native_concept",
            ConceptBlueprint(
                definition="A concept that refines multiple concepts",
                refines=[f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}", "CustomConcept", "other_domain.OtherConcept"],
            ),
            [f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}", "test_domain.CustomConcept", "other_domain.OtherConcept"],
        ),
        (
            "all_native_list",
            ConceptBlueprint(
                definition="A concept that refines only native concepts",
                refines=[NativeConceptEnum.TEXT.value, f"{SpecialDomain.NATIVE}.{NativeConceptEnum.IMAGE.value}", NativeConceptEnum.PDF.value],
            ),
            [
                f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}",
                f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.IMAGE.value}",
                f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.PDF.value}",
            ],
        ),
        (
            "all_domain_list",
            ConceptBlueprint(definition="A concept that refines only domain concepts", refines=["Concept1", "Concept2", "Concept3"]),
            ["test_domain.Concept1", "test_domain.Concept2", "test_domain.Concept3"],
        ),
        ("empty_refines", ConceptBlueprint(definition="A concept with no refines"), []),
        ("empty_list_refines", ConceptBlueprint(definition="A concept with empty list refines", refines=[]), []),
    ]
