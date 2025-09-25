from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint


class PipeSequenceSpec(PipeSpec):
    """Spec for sequential pipe execution in the Pipelex framework.

    PipeSequence orchestrates the execution of multiple pipes in a defined order,
    where each pipe's output can be used as input for subsequent pipes. This enables
    building complex data processing workflows with step-by-step transformations.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
        type: Fixed to "PipeSequence" for this pipe type.
        steps: Ordered list of SubPipeBlueprint instances defining the pipes
              to execute. Each step runs after the previous one completes,
              with access to all prior outputs in the context.

    Validation Rules:
        1. Steps list must not be empty.
        2. Each step must be a valid SubPipeBlueprint instance.
        3. Pipe codes referenced in steps must exist in the pipeline.

    """

    type: Literal["PipeSequence"] = "PipeSequence"
    category: Literal["PipeController"] = "PipeController"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    steps: list[SubPipeSpec]

    @override
    def to_blueprint(self) -> PipeSequenceBlueprint:
        base_blueprint = super().to_blueprint()
        core_steps = [step.to_blueprint() for step in self.steps]
        return PipeSequenceBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            steps=core_steps,
        )
