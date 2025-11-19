from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory, InputRequirementsFactoryError
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_required_concept
from pipelex.pipe_controllers.condition.exceptions import PipeConditionFactoryError
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint


class PipeConditionFactory(PipeFactoryProtocol[PipeConditionBlueprint, PipeCondition]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeConditionBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeCondition:
        # Parse output to strip multiplicity brackets
        try:
            output_parse_result = parse_concept_with_multiplicity(blueprint.output)
        except PipeVariableMultiplicityError as exc:
            msg = f"Error parsing concept with multiplicity for PipeCondition: {exc}"
            raise PipeConditionFactoryError(msg) from exc

        try:
            output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                domain=domain,
                concept_string_or_code=output_parse_result.concept,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
        except ConceptFactoryError as exc:
            msg = f"Error making domain and concept code for PipeCondition: {exc}"
            raise PipeConditionFactoryError(msg) from exc

        try:
            inputs = InputRequirementsFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
        except InputRequirementsFactoryError as exc:
            msg = f"Error making input requirements for PipeCondition: {exc}"
            raise PipeConditionFactoryError(msg) from exc

        output = get_required_concept(
            concept_string=ConceptFactory.make_concept_string_with_domain(
                domain=output_domain_and_code.domain,
                concept_code=output_domain_and_code.concept_code,
            ),
        )

        # Compute expression from expression_template or expression in blueprint
        if blueprint.expression_template:
            expression = blueprint.expression_template
        elif blueprint.expression:
            expression = "{{ " + blueprint.expression + " }}"
        else:
            msg = "PipeCondition must have either expression_template or expression"
            raise PipeConditionFactoryError(msg)

        return PipeCondition(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=inputs,
            output=output,
            expression=expression,
            outcome_map=blueprint.outcomes,
            default_outcome=blueprint.default_outcome,
            add_alias_from_expression_to=blueprint.add_alias_from_expression_to,
        )
