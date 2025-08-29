from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list


class SubPipeBlueprint(BaseModel):
    """
    SubPipeBlueprint is used to charaterize a step in a Pipe Controller (PipeSequence, PipeParallel, PipeBatch, PipeCondition).
    It should have no more than '1' of nb_output or multiple_output.
    When batch_over is specified, batch_as must also be provided.
    When batch_as is specified, batch_over must also be provided.
    """

    model_config = ConfigDict(extra="forbid")

    pipe: str = Field(description="The pipe code to run.")
    result: Optional[str] = Field(default=None, description="The name to assign to the output of the pipe.")
    nb_output: Optional[int] = Field(default=None, description="The number of outputs to generate.")
    multiple_output: Optional[bool] = Field(
        default=None,
        description="Whether to generate multiple outputs. (if yes, it leaves to the LLM the choice of the number of outputs)",
    )
    batch_over: Union[bool, str] = Field(default=False, description="The name of the list in the context to iterate over.")
    batch_as: Optional[str] = Field(default=None, description="The name to assign to the current item in the batch.")

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
