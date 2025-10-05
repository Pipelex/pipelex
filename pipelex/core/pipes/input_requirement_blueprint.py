from pydantic import BaseModel, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.pipe_run.pipe_run_params import PipeOutputMultiplicity


class InputRequirementBlueprint(BaseModel):
    concept: str
    multiplicity: PipeOutputMultiplicity | None = None

    @field_validator("concept", mode="before")
    @classmethod
    def validate_concept_string(cls, concept_string: str) -> str:
        ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=concept_string)
        return concept_string
