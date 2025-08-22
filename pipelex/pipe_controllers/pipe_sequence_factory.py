from typing import List, Literal

from typing_extensions import override

from pipelex.core.concepts.concept import Concept, NativeConceptEnum
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
    ) -> PipeSequence:
        pipe_steps = [SubPipeFactory.make_from_blueprint(step) for step in pipe_blueprint.steps]

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
        return PipeSequence(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            output=output,
            sequential_sub_pipes=pipe_steps,
        )
