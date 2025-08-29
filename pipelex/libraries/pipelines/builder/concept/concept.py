from pydantic import Field

from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint as ConceptBlueprintBaseModel,
)
from pipelex.core.concepts.concept_blueprint import (
    ConceptStructureBlueprint as ConceptStructureBlueprintBaseModel,
)
from pipelex.core.stuffs.stuff_content import StructuredContent


class ConceptSpec(StructuredContent):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")
    description: str = Field(description="Description of the concept, in natural language.")
    structure: str = Field(description="A description of a dict with fieldnames as keys, and values being a "
                           "dict with: definition, type, item_type, key_type, value_type, choices, required, default_value")


class ConceptStructureBlueprint(ConceptStructureBlueprintBaseModel, StructuredContent):
    field_name: str = Field(description="Field name in a pydantic model. Must be snake_case.")


class ConceptBlueprint(ConceptBlueprintBaseModel, StructuredContent):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")
