from typing import Dict, Optional

from pipelex.core.concepts.concept import Concept, NativeConceptEnum
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
        concept: Optional[Concept] = None
        for var_name, input_requirement_blueprint in blueprint.items():
            concept = None
            concept_string = input_requirement_blueprint.concept_code
            Concept.validate_concept_string(concept_string)

            if "." not in concept_string:
                if Concept.is_native_concept_code(concept_code=concept_string):
                    concept = get_concept_provider().get_native_concept(native_concept=NativeConceptEnum(concept_string))
                else:
                    concept = get_concept_provider().get_required_concept(
                        concept_string=Concept.construct_concept_string_with_domain(domain=domain, concept_code=concept_string)
                    )
            else:
                concept = get_concept_provider().get_required_concept(concept_string=concept_string)

            inputs[var_name] = InputRequirement(
                concept=concept,
                multiplicity=input_requirement_blueprint.multiplicity,
            )
        return PipeInputSpec(root=inputs)
