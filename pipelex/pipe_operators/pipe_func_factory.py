from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
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
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeFunc:
        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=pipe_blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeFunc(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            function_name=pipe_blueprint.function_name,
        )
