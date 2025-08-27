from typing import List, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint, PipeConditionPipeMapBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_details import PipeConditionPipeMap


class PipeConditionFactory(PipeFactoryProtocol[PipeConditionBlueprint, PipeCondition]):
    @classmethod
    def make_pipe_condition_pipe_map(cls, pipe_map: PipeConditionPipeMapBlueprint) -> List[PipeConditionPipeMap]:
        return [
            PipeConditionPipeMap(expression_result=expression_result, pipe_code=pipe_code) for expression_result, pipe_code in pipe_map.root.items()
        ]

    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeConditionBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeCondition:
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=blueprint.output_concept_string_or_concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeCondition(
            domain=domain,
            code=pipe_code,
            definition=blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(
                    domain=output_domain_and_code.domain, concept_code=output_domain_and_code.concept_code
                )
            ),
            expression_template=blueprint.expression_template,
            expression=blueprint.expression,
            pipe_map=cls.make_pipe_condition_pipe_map(pipe_map=blueprint.pipe_map),
            default_pipe_code=blueprint.default_pipe_code,
            add_alias_from_expression_to=blueprint.add_alias_from_expression_to,
        )
