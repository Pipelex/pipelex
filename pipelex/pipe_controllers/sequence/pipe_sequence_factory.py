from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory

if TYPE_CHECKING:
    from pipelex.pipe_controllers.sub_pipe import SubPipe


class PipeSequenceFactory(PipeFactoryProtocol[PipeSequenceBlueprint, PipeSequence]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeSequenceBlueprint,
    ) -> PipeSequence:
        sequential_sub_pipes: list[SubPipe] = []
        for step in blueprint.steps:
            sub_pipe = SubPipeFactory.make_from_blueprint(blueprint=step)
            sequential_sub_pipes.append(sub_pipe)

        return PipeSequence(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            sequential_sub_pipes=sequential_sub_pipes,
        )
