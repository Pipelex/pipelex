from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint, SubPipeFactory


class PipeSequenceBlueprint(PipeBlueprint):
    type: Literal["PipeSequence"] = "PipeSequence"
    steps: List[SubPipeBlueprint]


class PipeSequenceFactory(PipeFactoryProtocol[PipeSequenceBlueprint, PipeSequence]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeSequenceBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeSequence:
        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=pipe_blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeSequence(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            sequential_sub_pipes=[
                SubPipeFactory.make_from_blueprint(blueprint=step, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain)
                for step in pipe_blueprint.steps
            ],
        )
