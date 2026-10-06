from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.pipe_controllers.binding.binding_step_blueprint import BindingStepBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol

if TYPE_CHECKING:
    from pipelex.pipe_controllers.sequence.sequence_typed_flow import SequenceStep


class PipeSequenceFactory(PipeFactoryProtocol[PipeSequenceBlueprint, PipeSequence]):
    @classmethod
    @override
    def make(
        cls,
        *,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeSequenceBlueprint,
    ) -> PipeSequence:
        sequential_sub_pipes: list[SequenceStep] = []

        for step in blueprint.steps:
            if isinstance(step, BindingStepBlueprint):
                sequential_sub_pipes.append(BindingStep(from_path=step.from_path, output_name=step.result))
            else:
                sequential_sub_pipes.append(SubPipeFactory.make_from_blueprint(blueprint=step))

        return PipeSequence(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            sequential_sub_pipes=sequential_sub_pipes,
        )
