from typing import Any

from pydantic import BaseModel

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.variable_multiplicity import (
    PresenceMarker,
    VariableMultiplicity,
    format_concept_with_multiplicity,
    is_multiple_multiplicity,
)


class StuffSpec(BaseModel):
    concept: Concept
    multiplicity: VariableMultiplicity | None = None
    presence: PresenceMarker = PresenceMarker.PLAIN

    def is_multiple(self) -> bool:
        return is_multiple_multiplicity(multiplicity=self.multiplicity)

    def to_bundle_representation(self, *, relative_to_domain: str | None = None) -> str:
        """Render this spec as a bundle ref string (concept + multiplicity + presence marker).

        When ``relative_to_domain`` is given, the concept renders the way an author in that
        domain would write it: bare code when the concept is native or lives in that domain,
        qualified ``domain.Code`` otherwise. Without it, the concept ref is always qualified.
        """
        if relative_to_domain is None:
            concept_ref = self.concept.concept_ref
        elif self.concept.domain_code == relative_to_domain:
            concept_ref = self.concept.code
        else:
            concept_ref = self.concept.simple_concept_ref
        return format_concept_with_multiplicity(
            concept_ref,
            multiplicity=self.multiplicity,
            presence=self.presence,
        )

    def render_stuff_spec(self, *, concept_provider: ConceptProviderAbstract, output_format: ConceptRepresentationFormat) -> dict[str, Any]:
        """Render a representation of this stuff spec.

        Args:
            concept_provider: Resolves this spec's concept into its structure class. This is the one
                place in the whole render chain that resolves a class, so a caller states which
                library it means instead of every renderer reaching for one.
            output_format: The format to generate (JSON or PYTHON)

        Returns:
            Dictionary with concept and content structure,
            wrapped in a list if multiplicity indicates multiple items.
        """
        if not self.concept.declares_a_structure_class:
            # `native.Anything` deliberately has no structure class: asking the provider for one
            # is a category error, not a missing registration — render structureless instead.
            json_value, _ = self.concept.render_structureless_representation(
                output_format=output_format,
                multiplicity=self.multiplicity,
            )
            return json_value
        json_value, _ = self.concept.render_concept_representation(
            structure_class=concept_provider.get_structure_class(concept=self.concept),
            output_format=output_format,
            multiplicity=self.multiplicity,
        )
        return json_value
