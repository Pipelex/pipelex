from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.core.exceptions import StaticValidationError, StaticValidationErrorType
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

class PipeImgGenBlueprintValueError(ValueError):
    pass

class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_prompt: str | None = None
    img_gen_prompt_var_name: str | None = None

    model: ImgGenModelChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: OutputFormat | None = Field(default=None, strict=False)

    @override
    def _validate_inputs(self):
        # check that we have either an img_gen_prompt passed as attribute or as a single text input
        if not self.inputs:
            if not self.img_gen_prompt:
                msg = "No inputs provided, and not prompt."
                raise PipeImgGenBlueprintValueError(msg)

        nb_inputs = self.nb_inputs
        if nb_inputs > 1:
            too_many_candidate_inputs_error = StaticValidationError(
                error_type=StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS,
                variable_names=self.input_names,
                explanation="Only one text input can be provided for image gen prompt",
            )
            raise too_many_candidate_inputs_error

    @override
    def _validate_output(self):
        pass
