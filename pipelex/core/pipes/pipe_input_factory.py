from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_input import InputRequirement, PipeInputSpec
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.hub import get_concept_provider


class PipeInputSpecFactory:
    @classmethod
    def make_empty(cls) -> PipeInputSpec:
        return PipeInputSpec(root={})

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        blueprint: dict[str, str | InputRequirementBlueprint],
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeInputSpec:
        inputs: dict[str, InputRequirement] = {}
        for var_name, input_requirement_blueprint in blueprint.items():
            if isinstance(input_requirement_blueprint, str):
                input_requirement_blueprint = InputRequirementBlueprint(concept=input_requirement_blueprint)

            concept_string = input_requirement_blueprint.concept
            ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=concept_string)
            input_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                domain=domain,
                concept_string_or_code=concept_string,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )

            inputs[var_name] = InputRequirement(
                concept=get_concept_provider().get_required_concept(
                    concept_string=ConceptFactory.construct_concept_string_with_domain(
                        domain=input_domain_and_code.domain,
                        concept_code=input_domain_and_code.concept_code,
                    ),
                ),
                multiplicity=input_requirement_blueprint.multiplicity,
            )
        return PipeInputSpec(root=inputs)
