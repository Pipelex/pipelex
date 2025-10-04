from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.input_requirements import InputRequirement, InputRequirements
from pipelex.hub import get_required_concept


class InputRequirementsFactory:
    @classmethod
    def make_empty(cls) -> InputRequirements:
        return InputRequirements(root={})

    @classmethod
    def make_from_blueprint(
        cls,
        domain: str,
        blueprint: dict[str, str | InputRequirementBlueprint],
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> InputRequirements:
        input_requirements_dict: dict[str, InputRequirement] = {}
        for var_name, input_requirement_blueprint in blueprint.items():
            if isinstance(input_requirement_blueprint, str):
                input_requirement_blueprint = InputRequirementBlueprint(concept=input_requirement_blueprint)

            concept_string_or_code = input_requirement_blueprint.concept
            ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=concept_string_or_code)
            concept_string_with_domain = ConceptFactory.make_concept_string_with_domain_from_concept_string_or_code(
                domain=domain,
                concept_sring_or_code=concept_string_or_code,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )

            input_requirements_dict[var_name] = InputRequirement(
                concept=get_required_concept(concept_string=concept_string_with_domain),
                multiplicity=input_requirement_blueprint.multiplicity,
            )
        return InputRequirements(root=input_requirements_dict)
