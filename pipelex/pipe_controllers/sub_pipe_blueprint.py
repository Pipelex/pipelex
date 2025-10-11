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
    batch_over: str | None = None
    batch_as: str | None = None

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if has_more_than_one_among_attributes_from_list(self, attributes_list=["nb_output", "multiple_output"]):
            msg = "PipeStepBlueprint should have no more than '1' of nb_output or multiple_output"
            raise PipeDefinitionError(msg)
        return self

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        if self.batch_over and not self.batch_as:
            msg = f"In pipe '{self.pipe}': When 'batch_over' is specified, 'batch_as' must also be provided"
            raise PipeDefinitionError(msg)

        if self.batch_as and not self.batch_over:
            msg = f"In pipe '{self.pipe}': When 'batch_as' is specified, 'batch_over' must also be provided"
            raise PipeDefinitionError(msg)

        return self
