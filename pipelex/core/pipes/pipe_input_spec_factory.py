from typing import Dict

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_input_spec import InputRequirement, InputRequirementBlueprint, PipeInputSpec
from pipelex.hub import get_concept_provider


class PipeInputSpecFactory:
    """Factory for creating PipeInputSpec instances with dependencies."""

    @classmethod
    def make_empty(cls) -> PipeInputSpec:
        return PipeInputSpec(root={})

    @classmethod
    def make_from_blueprint(cls, domain: str, blueprint: Dict[str, InputRequirementBlueprint]) -> PipeInputSpec:
        inputs: Dict[str, InputRequirement] = {}
        for var_name, input_requirement_blueprint in blueprint.items():
            concept_string = input_requirement_blueprint.concept_code
            Concept.validate_concept_string(concept_string)

            inputs[var_name] = InputRequirement(
                concept=get_concept_provider().get_required_concept(concept_string=concept_string, domain=domain),
                multiplicity=input_requirement_blueprint.multiplicity,
            )
        return PipeInputSpec(root=inputs)
