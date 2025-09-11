from typing import Optional

from pydantic import field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint as InputRequirementBlueprintCore

class InputRequirementBlueprint(StructuredContent):
    """Blueprint specifying input requirements for a pipe in the Pipelex framework.

    Defines the concept type and multiplicity constraints for pipe inputs, ensuring
    proper data validation and flow control in pipeline execution.

    Attributes:
        concept: The concept code or concept string for the input. Must be in PascalCase
                format. When using concept strings, format is "domain.ConceptCode" with
                domain in lowercase and ConceptCode in PascalCase.
        multiplicity: Optional constraint on input cardinality (e.g., single, multiple).
                     Defines how many instances of the concept the pipe can process.

    Validation Rules:
        1. Concept must be a valid concept code (PascalCase) or concept string (domain.ConceptCode).
        2. Domain and concept code are separated by a dot when using full concept strings.
        3. Concept validation is performed using ConceptBlueprint.validate_concept_string_or_concept_code.

    Raises:
        ValidationError: When concept format is invalid or doesn't meet PascalCase requirements.
    """

    concept: str
    multiplicity: Optional[PipeOutputMultiplicity] = None

    @field_validator("concept", mode="before")
    @classmethod
    def validate_concept_string(cls, concept_string: str) -> str:
        ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=concept_string)
        return concept_string

    def to_core_input_requirement(self, domain: str) -> InputRequirementBlueprintCore:
        """Convert this InputRequirementBlueprint to the core InputRequirement."""

        return InputRequirementBlueprintCore(concept=self.concept, multiplicity=self.multiplicity)
