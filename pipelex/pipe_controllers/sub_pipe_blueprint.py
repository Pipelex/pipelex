from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list


class SubPipeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipe: str
    result: Optional[str] = None
    nb_output: Optional[int] = None
    multiple_output: Optional[bool] = None
    batch_over: Union[bool, str] = False
    batch_as: Optional[str] = None

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if has_more_than_one_among_attributes_from_list(self, attributes_list=["nb_output", "multiple_output"]):
            raise PipeDefinitionError("PipeStepBlueprint should have no more than '1' of nb_output or multiple_output")
        return self

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        batch_over_is_specified = self.batch_over is not False and self.batch_over != ""
        batch_as_is_specified = self.batch_as is not None and self.batch_as != ""

        if batch_over_is_specified and not batch_as_is_specified:
            raise PipeDefinitionError(f"In pipe '{self.pipe}': When 'batch_over' is specified, 'batch_as' must also be provided")

        if batch_as_is_specified and not batch_over_is_specified:
            raise PipeDefinitionError(f"In pipe '{self.pipe}': When 'batch_as' is specified, 'batch_over' must also be provided")

        return self
