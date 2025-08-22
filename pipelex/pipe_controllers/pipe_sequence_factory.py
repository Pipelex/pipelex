from typing import List, Literal

from typing_extensions import override

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
        return PipeSequence(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            output=get_concept_provider().get_required_concept(concept_string=pipe_blueprint.output, domain=domain),
            sequential_sub_pipes=[SubPipeFactory.make_from_blueprint(step) for step in pipe_blueprint.steps],
        )
