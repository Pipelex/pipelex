"""The generator's required+default invariant (S2 E3): the blueprint validator rejects the pair
upstream, so a field carrying both reaching the generator is a bug — it must raise, not silently
drop the required marker by parameter ordering (the accident S1 measured). The pair is smuggled
past validation with `model_construct`, exactly how a future bypass would reach the generator.
"""

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator


class TestStructureGeneratorRequiredDefaultInvariant:
    def test_required_with_default_raises_instead_of_dropping_required(self) -> None:
        contradictory_field = ConceptStructureBlueprint.model_construct(
            description="required AND default together",
            type=ConceptStructureBlueprintFieldType.TEXT,
            required=True,
            default_value="Untitled",
        )
        with pytest.raises(ConceptStructureGeneratorError, match="required AND carries default_value"):
            StructureGenerator().generate_from_structure_blueprint(
                class_name="ContradictoryModel", structure_blueprint={"titled_default": contradictory_field}
            )
