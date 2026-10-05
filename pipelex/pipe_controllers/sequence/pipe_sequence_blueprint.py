from typing import Annotated, Any, Literal

from pydantic import Discriminator, Tag, field_validator
from typing_extensions import override

from pipelex.pipe_controllers.binding.binding_step_blueprint import (
    BindingStepBlueprint,
    check_binding_step_shape,
    is_binding_step_dict,
    raw_step_mapping,
)
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint

_PIPE_STEP_TAG = "pipe_step"
_BINDING_STEP_TAG = "binding_step"


def _sequence_step_kind(step: Any) -> str:  # kw-only: ignore
    """Which shape a sequence step takes: a binding step when it carries `from`, a pipe step otherwise."""
    if isinstance(step, BindingStepBlueprint):
        return _BINDING_STEP_TAG
    raw_step = raw_step_mapping(raw_step=step)
    if raw_step is not None and is_binding_step_dict(raw_step=raw_step):
        return _BINDING_STEP_TAG
    return _PIPE_STEP_TAG


# A step of a PipeSequence: a pipe step, which runs a pipe, or a binding step, which binds the value at a path
# in working memory to a new name. Each shape is a closed table, and a step carrying `from` is a binding step.
SequenceStepBlueprint = Annotated[
    Annotated[SubPipeBlueprint, Tag(_PIPE_STEP_TAG)] | Annotated[BindingStepBlueprint, Tag(_BINDING_STEP_TAG)],
    Discriminator(_sequence_step_kind),
]


class PipeSequenceBlueprint(PipeBlueprint):
    type: Literal["PipeSequence"] = "PipeSequence"
    pipe_category: Literal["PipeController"] = "PipeController"
    steps: list[SequenceStepBlueprint]

    @property
    def pipe_steps(self) -> list[SubPipeBlueprint]:
        """The steps that run a pipe, in order; a binding step runs none."""
        return [step for step in self.steps if isinstance(step, SubPipeBlueprint)]

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from the sequence's pipe steps."""
        return {step.pipe for step in self.pipe_steps}

    @property
    @override
    def ordered_pipe_dependencies(self) -> list[str]:
        """Return the ordered list of pipe codes from the sequence's pipe steps.

        For sequences, the order of steps matters, so we preserve it.
        """
        return [step.pipe for step in self.pipe_steps]

    @field_validator("steps", mode="before")
    @classmethod
    def validate_steps(cls, steps: list[Any]) -> list[Any]:
        if not steps:
            msg = "PipeSequence must have at least 1 step"
            raise ValueError(msg)
        for step_index, step in enumerate(steps):
            raw_step = raw_step_mapping(raw_step=step)
            if raw_step is not None:
                check_binding_step_shape(raw_step=raw_step, step_label=f"Step {step_index + 1} of the sequence")
        return steps

    @override
    def validate_inputs(self):
        pass

    @override
    def validate_output(self):
        pass
