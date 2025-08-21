from typing import Literal

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_operators.pipe_func import PipeFunc


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str


class PipeFuncFactory(PipeFactoryProtocol[PipeFuncBlueprint, PipeFunc]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeFuncBlueprint,
    ) -> PipeFunc:
        return PipeFunc(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            output=get_concept_provider().get_required_concept(
                concept_code=Concept.construct_concept_string_with_domain(domain=domain, concept_code=pipe_blueprint.output)
            ),
            function_name=pipe_blueprint.function_name,
        )
