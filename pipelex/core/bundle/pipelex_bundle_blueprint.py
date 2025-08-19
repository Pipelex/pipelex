from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from pipelex.core.concept.concept_blueprint import ConceptBlueprint
from pipelex.core.pipe.pipe_blueprint import PipeBlueprint


class PipelexBundleBlueprint(BaseModel):
    """Complete blueprint of a pipelex bundle TOML definition."""

    domain: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    concepts: Optional[Dict[str, ConceptBlueprint]] = Field(default_factory=dict)

    pipes: Optional[Dict[str, PipeBlueprint]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def model_validate_blueprint(self) -> Self:
        return self.validate_blueprint()

    def validate_blueprint(self) -> Self:
        if self.concepts is not None:
            self.concepts = {
                concept_name: ConceptBlueprint.model_validate(concept_blueprint) for concept_name, concept_blueprint in self.concepts.items()
            }
        if self.pipes is not None:
            self.pipes = {pipe_name: PipeBlueprint.model_validate(pipe_blueprint) for pipe_name, pipe_blueprint in self.pipes.items()}
        return self
