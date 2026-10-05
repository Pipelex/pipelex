from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_controllers.binding.binding_step import BindingStep, make_private_binding_name
from pipelex.pipe_controllers.binding.binding_step_blueprint import BindingStepBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import is_dotted_batch_over
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.pipe_controllers.sequence.sequence_typed_flow import SequenceStep


def _names_in_sequence(*, inputs: InputStuffSpecs, blueprint: PipeSequenceBlueprint) -> set[str]:
    """Every name the sequence's inputs and steps write or read, which a private name must not take."""
    names = set(inputs.root)
    for step in blueprint.steps:
        if isinstance(step, BindingStepBlueprint):
            names.update({step.root_name, step.result})
            continue
        for name in (step.result, step.batch_as):
            if name is not None:
                names.add(name)
        if step.batch_over is not None:
            names.add(get_root_from_dotted_path(step.batch_over))
    return names


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
        """Build the runtime sequence, writing each pipe step's dotted `batch_over` as a binding followed by a batch.

        `{ pipe = "describe_page", batch_over = "catalog.pages", batch_as = "page" }` becomes a binding step of `catalog.pages`
        under a private name, followed by the same step batching over that name, so the dotted path is typed, walked, copied,
        recorded absent and drawn exactly as a binding step's `from` is.
        """
        sequential_sub_pipes: list[SequenceStep] = []
        taken_names = _names_in_sequence(inputs=inputs, blueprint=blueprint)

        for step in blueprint.steps:
            if isinstance(step, BindingStepBlueprint):
                sequential_sub_pipes.append(BindingStep(from_path=step.from_path, output_name=step.result))
                continue
            pipe_step = step
            if step.batch_over is not None and is_dotted_batch_over(batch_over=step.batch_over):
                private_name = make_private_binding_name(path=step.batch_over, taken_names=taken_names)
                taken_names.add(private_name)
                sequential_sub_pipes.append(BindingStep(from_path=step.batch_over, output_name=private_name, is_dotted_batch_over=True))
                # A copy, never validated again: the private name is the runtime's own, outside the names an author writes.
                pipe_step = step.model_copy(update={"batch_over": private_name})
            sequential_sub_pipes.append(SubPipeFactory.make_from_blueprint(blueprint=pipe_step))

        return PipeSequence(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            sequential_sub_pipes=sequential_sub_pipes,
        )
