"""Test data for ConceptFactory._make_refines tests."""

from typing import ClassVar, List, Tuple

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain


class TestCases:
    """Test cases for ConceptFactory._make_refines method."""

    # Test cases with expected results - only native concepts can be refined
    TEST_CASES: ClassVar[List[Tuple[str, ConceptBlueprint, str]]] = [
        (
            "native_concept_string",
            ConceptBlueprint(definition="A concept that refines a native text concept", refines=NativeConceptEnum.TEXT.value),
            f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}",
        ),
        (
            "fully_qualified_native_string",
            ConceptBlueprint(
                definition="A concept that refines a fully qualified native concept",
                refines=f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}",
            ),
            f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}",
        ),
    ]
