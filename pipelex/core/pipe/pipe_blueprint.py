from typing import Dict, Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.concept.concept_code_factory import ConceptCodeFactory


class PipeBlueprint(BaseModel):
    """Simple data container for pipe blueprint information."""

    type: str
    definition: Optional[str] = None
    inputs: Optional[Dict[str, str]] = None
    output: str

    @model_validator(mode="after")
    def add_domain_prefix(self) -> Self:
        if self.inputs:
            for input_name, input_concept_code in self.inputs.items():
                self.inputs[input_name] = ConceptCodeFactory.make_concept_code_from_str(
                    concept_str=input_concept_code,
                    fallback_domain="implicit",
                )
        self.output = ConceptCodeFactory.make_concept_code_from_str(
            concept_str=self.output,
            fallback_domain="implicit",
        )
        return self
