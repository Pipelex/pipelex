from typing import Dict, List, Literal, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.core.concepts.concept import Concept, NativeConceptEnum
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.pipe_condition import PipeCondition
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionPipeMap

PipeConditionPipeMapRoot = Dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    root: PipeConditionPipeMapRoot = Field(default_factory=dict)


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None


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
        pipe_blueprint: PipeConditionBlueprint,
    ) -> PipeCondition:
        output_concept_code = pipe_blueprint.output
        if "." not in output_concept_code:
            if Concept.is_native_concept_code(concept_code=output_concept_code):
                output = get_concept_provider().get_native_concept(native_concept=NativeConceptEnum(output_concept_code))
            else:
                output = get_concept_provider().get_required_concept(
                    concept_string=Concept.construct_concept_string_with_domain(domain=domain, concept_code=output_concept_code)
                )
        else:
            output = get_concept_provider().get_required_concept(concept_string=output_concept_code)
        return PipeCondition(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            output=output,
            expression_template=pipe_blueprint.expression_template,
            expression=pipe_blueprint.expression,
            pipe_map=cls.make_pipe_condition_pipe_map(pipe_map=pipe_blueprint.pipe_map),
            default_pipe_code=pipe_blueprint.default_pipe_code,
            add_alias_from_expression_to=pipe_blueprint.add_alias_from_expression_to,
        )
