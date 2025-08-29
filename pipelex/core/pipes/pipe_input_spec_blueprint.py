from typing import Optional

from pydantic import BaseModel, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity


class InputRequirementBlueprint(BaseModel):
    """
    InputRequirementBlueprint is used to specify the input requirements for a pipe.
    For the concept_code, it has to be a valid concept code: PascalCase format.
    Attach the domain to the concept code with a dot between the 2.
    """

    concept: str = Field(description="The concept code of the input: Should be PascalCase format")
    multiplicity: Optional[PipeOutputMultiplicity] = Field(default=None, description="The multiplicity of the input.")

    @field_validator("concept", mode="before")
    @classmethod
    def validate_concept_string(cls, concept_string: str) -> str:
        ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=concept_string)
        return concept_string
