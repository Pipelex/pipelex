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
        """Convert the StuffSpec to its bundle string representation.

        Generates a string format used in bundle definitions, with bracket notation
        indicating multiplicity when applicable.

        Returns:
            A string representation combining the concept reference with optional
            multiplicity brackets.

        Examples:
            - multiplicity=None -> "native.Text" (single item)
            - multiplicity=True -> "native.Text[]" (unbounded list)
            - multiplicity=3 -> "native.Text[3]" (exactly 3 items)
        """
        if self.multiplicity is None:
            return self.concept.concept_ref
        if isinstance(self.multiplicity, bool):
            return f"{self.concept.concept_ref}[]"
        return f"{self.concept.concept_ref}[{self.multiplicity}]"
