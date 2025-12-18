from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class StuffSpec(BaseModel):
    concept: Concept
    # TODO: Why None here ? Why not just false ?
    multiplicity: VariableMultiplicity | None = None

    def is_multiple(self) -> bool:
        if self.multiplicity is None:
            return False
        if isinstance(self.multiplicity, bool):
            return self.multiplicity
        return self.multiplicity > 1
