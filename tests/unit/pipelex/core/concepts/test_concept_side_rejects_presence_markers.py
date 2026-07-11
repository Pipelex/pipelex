import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid


class TestConceptSideRejectsPresenceMarkers:
    """`?` and `!` are slot markers: they are never legal on concept definitions, `refines`,
    structure-field refs, or package refs (D1). Presence is a property of the flow, not of concepts.
    """

    @pytest.mark.parametrize("ref", ["Text?", "Text!", "domain.Concept?", "domain.Concept!", "Text[]?", "alias->domain.Concept?"])
    def test_concept_ref_or_code_with_marker_is_invalid(self, ref: str):
        assert not is_concept_ref_or_code_valid(ref)

    @pytest.mark.parametrize("refines", ["Text?", "Text!", "domain.Base?"])
    def test_refines_with_marker_rejected(self, refines: str):
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(description="a concept", refines=refines)

    @pytest.mark.parametrize("concept_ref", ["Clause?", "Clause!", "legal.Clause?"])
    def test_structure_field_concept_ref_with_marker_rejected(self, concept_ref: str):
        with pytest.raises(ValidationError):
            ConceptStructureBlueprint(
                description="a field",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref=concept_ref,
            )

    @pytest.mark.parametrize("item_concept_ref", ["Clause?", "Clause!"])
    def test_structure_field_item_concept_ref_with_marker_rejected(self, item_concept_ref: str):
        with pytest.raises(ValidationError):
            ConceptStructureBlueprint(
                description="a list field",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_concept_ref=item_concept_ref,
            )
