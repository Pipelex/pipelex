from typing import Any

from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity, format_concept_with_multiplicity


class StuffSpec(BaseModel):
    concept: Concept
    multiplicity: VariableMultiplicity | None = None
    presence: PresenceMarker = PresenceMarker.PLAIN

    def is_multiple(self) -> bool:
        if self.multiplicity is None:
            return False
        if isinstance(self.multiplicity, bool):
            return self.multiplicity
        return self.multiplicity > 1

    def to_bundle_representation(self) -> str:
        return format_concept_with_multiplicity(
            self.concept.concept_ref,
            multiplicity=self.multiplicity,
            presence=self.presence,
        )

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
