from typing import Callable

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.hub import get_native_concept


class TestConceptLibrary:
    def test_is_image_concept(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        native_image_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE)

        concept_1 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                structure="ImageContent",
            ),
        )

        concept_2 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept2",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                refines="native.Image",
            ),
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept2",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                refines="Image",
            ),
        )

        concept_4 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept4",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                structure="ImageContent",
            ),
        )

        concept_5 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept5",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                structure="TextContent",
            ),
        )

        concept_6 = ConceptFactory.make_from_blueprint(
            domain="test",
            concept_code="TestConcept6",
            blueprint=ConceptBlueprint(
                description="Lorem Ipsum",
                structure="PDFContent",
            ),
        )

        assert (
            Concept.are_concept_compatible(
                concept_1=native_image_concept, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True
            )
            is True
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_1, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is True
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_2, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is True
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_3, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is True
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_4, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is True
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_5, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is False
        )
        assert (
            Concept.are_concept_compatible(concept_1=concept_6, concept_2=get_native_concept(native_concept=NativeConceptCode.IMAGE), strict=True)
            is False
        )
