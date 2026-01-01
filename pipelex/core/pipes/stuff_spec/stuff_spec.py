from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class StuffSpec(BaseModel):
    concept: Concept
    multiplicity: VariableMultiplicity | None = None

    def is_multiple(self) -> bool:
        if self.multiplicity is None:
            return False
        if isinstance(self.multiplicity, bool):
            return self.multiplicity
        return self.multiplicity > 1

    def to_bundle_representation(self) -> str:
        if self.multiplicity is None:
            return self.concept.concept_ref
        if isinstance(self.multiplicity, bool):
            return f"{self.concept.concept_ref}[]"
        return f"{self.concept.concept_ref}[{self.multiplicity}]"
