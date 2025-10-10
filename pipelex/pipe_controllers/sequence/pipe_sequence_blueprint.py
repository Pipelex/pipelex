from typing import Literal

from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceBlueprint(PipeBlueprint):
    type: Literal["PipeSequence"] = "PipeSequence"
    pipe_category: Literal["PipeController"] = "PipeController"
    steps: list[SubPipeBlueprint]

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from the sequence steps."""
        return {step.pipe for step in self.steps}

    @property
    @override
    def ordered_pipe_dependencies(self) -> list[str]:
        """Return the ordered list of pipe codes from the sequence steps.

        For sequences, the order of steps matters, so we preserve it.
        """
        return [step.pipe for step in self.steps]
