# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Self, Union

from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.core.pipe_run_params import BatchParams, make_output_multiplicity
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.tools.utils.validation_utils import has_more_than_one_among_attributes_from_list


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
            raise PipeDefinitionError("PipeStepBlueprint should have no more than one of nb_output or multiple_output")
        return self

    def make_sub_pipe(self) -> SubPipe:
        output_multiplicity = make_output_multiplicity(
            nb_output=self.nb_output,
            multiple_output=self.multiple_output,
        )
        batch_params = BatchParams.make_optional_batch_params(
            input_list_name=self.batch_over,
            input_item_name=self.batch_as,
        )
        return SubPipe(
            pipe_code=self.pipe,
            output_name=self.result,
            output_multiplicity=output_multiplicity,
            batch_params=batch_params,
        )
