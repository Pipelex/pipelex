from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.binding.binding_step_blueprint import PATH_GRAMMAR_DESCRIPTION
from pipelex.pipe_machinery.validation import check_name_is_not_reserved, check_stored_name
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

    # Every refusal below names the step by the pipe it runs: the faulty fields are the step's, held by the sequence or the
    # parallel that the error locates, not the pipe's, and the blueprint does not know the code of the pipe holding it.
    @property
    def step_label(self) -> str:
        """How a message names the step, after "the": the step by the pipe it runs."""
        return f"step running pipe '{self.pipe}'"

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if has_more_than_one_among_attributes_from_list(self, attributes_list=["nb_output", "multiple_output"]):
            msg = f"The {self.step_label} carries both `nb_output` and `multiple_output`: a step sets at most one of them."
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        if self.batch_over and not self.batch_as:
            msg = (
                f"The {self.step_label} carries `batch_over` without `batch_as`: a step batching over a list hands each item to its pipe "
                "under the name `batch_as` gives it."
            )
            raise ValueError(msg)

        if self.batch_as and not self.batch_over:
            msg = (
                f"The {self.step_label} carries `batch_as` without `batch_over`: `batch_as` names each item of the list a step batches over, "
                "and `batch_over` names that list."
            )
            raise ValueError(msg)

        if self.batch_over and self.batch_as and self.batch_over == self.batch_as:
            msg = (
                f"The `batch_as` of the {self.step_label} is '{self.batch_as}', the same name as its `batch_over`: each item needs a name "
                'of its own. Use a plural for `batch_over` and its singular for `batch_as`, such as `batch_over = "items"` and '
                '`batch_as = "item"`.'
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
            f"The dotted `batch_over` '{self.batch_over}' of the {self.step_label} is not a path. A dotted `batch_over` binds the list "
            f"at its path, as a binding step's `from` does, and a path is {PATH_GRAMMAR_DESCRIPTION}."
        )
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID, variable_names=[self.batch_over])

    @model_validator(mode="after")
    def validate_stored_names(self) -> Self:
        """Hold the names the step stores values under to the input-name form, and keep a plain `batch_over` off the reserved
        prefix, on a sequence step and a parallel branch alike.

        A step stores its `result` and hands each item to its pipe under `batch_as`, both in working memory, for a pipe to read
        through an input, so each is a stored name and takes the plain input-name form. A plain `batch_over` reads a name rather
        than storing one, and only stays off the prefix the runtime reserves for the bound list of a dotted `batch_over`: a nested
        sequence binds in its caller's working memory, so a step batching over a name taking the prefix could read a list a
        sequence it calls binds. A dotted `batch_over` follows the path grammar, whose segments are never underscore-led.
        """
        for field_name, name in (("result", self.result), ("batch_as", self.batch_as)):
            if name is not None:
                check_stored_name(name=name, field_label=f"The `{field_name}` of the {self.step_label}")
        if self.batch_over is not None:
            check_name_is_not_reserved(name=self.batch_over, field_label=f"The `batch_over` of the {self.step_label}")
        return self
