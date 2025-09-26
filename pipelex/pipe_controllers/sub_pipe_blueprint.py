from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list
from pipelex.types import Self


class SubPipeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipe: str
    result: str | None = None
    nb_output: int | None = None
    multiple_output: bool | None = None
    batch_over: bool | str = False
    batch_as: str | None = None

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if has_more_than_one_among_attributes_from_list(self, attributes_list=["nb_output", "multiple_output"]):
            msg = "PipeStepBlueprint should have no more than '1' of nb_output or multiple_output"
            raise PipeDefinitionError(msg)
        return self

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        batch_over_is_specified = self.batch_over is not False and self.batch_over != ""
        batch_as_is_specified = self.batch_as is not None and self.batch_as != ""

        if batch_over_is_specified and not batch_as_is_specified:
            msg = f"In pipe '{self.pipe}': When 'batch_over' is specified, 'batch_as' must also be provided"
            raise PipeDefinitionError(msg)

        if batch_as_is_specified and not batch_over_is_specified:
            msg = f"In pipe '{self.pipe}': When 'batch_as' is specified, 'batch_over' must also be provided"
            raise PipeDefinitionError(msg)

        return self
