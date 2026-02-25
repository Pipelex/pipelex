from typing import Any

from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
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

    def render_stuff_spec(self, output_format: ConceptRepresentationFormat) -> dict[str, Any]:
        """Render a representation of this stuff spec.

        Args:
            output_format: The format to generate (JSON or PYTHON)

        Returns:
            Dictionary with concept and content structure,
            wrapped in a list if multiplicity indicates multiple items.
        """
        json_value, _ = self.concept.render_concept_representation(
            output_format=output_format,
            is_multiple=self.is_multiple(),
        )
        return json_value
