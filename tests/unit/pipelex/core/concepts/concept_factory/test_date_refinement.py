from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.date_content import DateContent


class TestDateRefinement:
    """A domain concept refining native Date resolves DateContent via the generic machinery."""

    def test_refining_date_resolves_date_content(self):
        """`refines = "Date"` builds a concept whose structure class inherits from DateContent."""
        concept = ConceptFactory.make_from_blueprint(
            domain_code="billing",
            concept_code="DueDate",
            blueprint_or_string_description=ConceptBlueprint(description="The date payment is due", refines="Date"),
        )

        structure_class = concept.get_structure_class()
        assert issubclass(structure_class, DateContent)

        native_date = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DATE)
        assert Concept.are_concept_compatible(concept_1=concept, concept_2=native_date, strict=True)
