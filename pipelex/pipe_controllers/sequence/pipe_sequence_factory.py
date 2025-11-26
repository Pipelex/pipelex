from typing import Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory


class PipeSequenceFactory(PipeFactoryProtocol[PipeSequenceBlueprint, PipeSequence]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        pipe_category: Any,
        pipe_type: str,
        code: str,
        domain: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeSequenceBlueprint,
    ) -> PipeSequence:
        return PipeSequence(
            domain=domain,
            code=code,
            description=description,
            inputs=inputs,
            output=output,
            sequential_sub_pipes=[SubPipeFactory.make_from_blueprint(blueprint=step) for step in blueprint.steps],
        )
