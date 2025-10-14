from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint


class PipeSequenceSpec(PipeSpec):
    """PipeSequenceSpec orchestrates the execution of multiple pipes in a defined order,
    where each pipe's output can be used as input for subsequent pipes. This enables
    building complex data processing workflows with step-by-step transformations.
    """

    type: SkipJsonSchema[Literal["PipeSequence"]] = "PipeSequence"
    pipe_category: SkipJsonSchema[Literal["PipeController"]] = "PipeController"
    steps: list[SubPipeSpec] = Field(
        description=("List of SubPipeSpec instances to execute sequentially. Each step runs after the previous one completes.")
    )

    @override
    def to_blueprint(self) -> PipeSequenceBlueprint:
        base_blueprint = super().to_blueprint()
        core_steps = [step.to_blueprint() for step in self.steps]
        return PipeSequenceBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            steps=core_steps,
        )
