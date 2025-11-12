from typing import Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.core.exceptions import StaticValidationError, StaticValidationErrorType
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeExtractBlueprint(PipeBlueprint):
    type: Literal["PipeExtract"] = "PipeExtract"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: ExtractModelChoice | None = None
    page_images: bool | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None

    @field_validator("output", mode="before")
    @classmethod
    def force_output(cls, _: str) -> str:
        return "Page[]"

    @override
    def _validate_inputs(self):
        nb_inputs = self.nb_inputs
        msg = (
            "Only one input must be provided for the PipeExtract, and it must be a pdf or an image or a concept that refines one of them."
            f"Only {nb_inputs} inputs were provided."
        )
        if self.inputs is None:
            raise StaticValidationError(
                error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                variable_names=self.input_names,
                explanation=msg,
            )
        if nb_inputs > 1:
            too_many_candidate_inputs_error = StaticValidationError(
                error_type=StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS,
                variable_names=self.input_names,
                explanation=msg,
            )
            raise too_many_candidate_inputs_error
        if nb_inputs < 1:
            missing_input_variable_error = StaticValidationError(
                error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                variable_names=self.input_names,
                explanation="For PipeExtract you must provide either a pdf or an image or a concept that refines one of them",
            )
            raise missing_input_variable_error

    @override
    def _validate_output(self):
        if self.output != "Page[]":
            msg = "PipeExtract output should be a Page concept, but is {self.output.concept_string}"
            raise StaticValidationError(
                error_type=StaticValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                variable_names=[self.output],
                explanation=msg,
            )
