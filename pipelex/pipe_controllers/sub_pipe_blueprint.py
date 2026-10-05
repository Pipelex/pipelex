from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.binding.binding_step_blueprint import PATH_GRAMMAR_DESCRIPTION
from pipelex.tools.misc.string_utils import is_field_path
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list
from pipelex.validation_error_types import PipeValidationErrorType


def is_dotted_batch_over(*, batch_over: str) -> bool:
    """Whether a `batch_over` is a dotted path, which a PipeSequence binds before batching over the bound list."""
    return "." in batch_over


class SubPipeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipe: str
    result: str | None = None
    nb_output: int | None = None
    multiple_output: bool | None = None
    batch_over: str | None = None
    batch_as: str | None = None

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if has_more_than_one_among_attributes_from_list(self, attributes_list=["nb_output", "multiple_output"]):
            msg = "PipeStepBlueprint should have no more than '1' of nb_output or multiple_output"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        if self.batch_over and not self.batch_as:
            msg = f"In pipe '{self.pipe}': When 'batch_over' is specified, 'batch_as' must also be provided"
            raise ValueError(msg)

        if self.batch_as and not self.batch_over:
            msg = f"In pipe '{self.pipe}': When 'batch_as' is specified, 'batch_over' must also be provided"
            raise ValueError(msg)

        if self.batch_over and self.batch_as and self.batch_over == self.batch_as:
            msg = (
                f"In pipe '{self.pipe}': 'batch_as' ('{self.batch_as}') must not be the same as "
                f"'batch_over' ('{self.batch_over}'). "
                f"Use a plural for batch_over and the singular form for batch_as "
                f"(e.g., batch_over='items', batch_as='item')."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION,
            )

        return self

    @model_validator(mode="after")
    def validate_dotted_batch_over(self) -> Self:
        """Refuse a dotted `batch_over` outside the path grammar: it binds the list at that path, as a binding step's `from` does."""
        if self.batch_over is None or not is_dotted_batch_over(batch_over=self.batch_over) or is_field_path(path=self.batch_over):
            return self
        msg = (
            f"In pipe '{self.pipe}': the dotted `batch_over` '{self.batch_over}' is not a path. A dotted `batch_over` binds the list "
            f"at its path, as a binding step's `from` does, and a path is {PATH_GRAMMAR_DESCRIPTION}."
        )
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID, variable_names=[self.batch_over])
