from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.libraries.concept.concept_library import ConceptLibrary


class TestYesNoRefinement:
    """A domain concept refining native YesNo resolves YesNoContent via the generic machinery."""

    def test_refining_yes_no_resolves_yes_no_content(self):
        """`refines = "YesNo"` builds a concept whose structure class inherits from YesNoContent."""
        concept = ConceptFactory.make_from_blueprint(
            domain_code="urgency",
            concept_code="IsUrgent",
            blueprint_or_string_description=ConceptBlueprint(description="Whether the item is urgent", refines="YesNo"),
        )

        library = ConceptLibrary.make_empty()
        structure_class = library.get_structure_class(concept=concept)
        assert issubclass(structure_class, YesNoContent)

        native_yes_no = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.YES_NO)
        assert library.is_compatible(tested_concept=concept, wanted_concept=native_yes_no, strict=True)
