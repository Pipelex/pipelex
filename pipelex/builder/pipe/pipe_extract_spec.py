from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.extract.extract_setting import ExtractModelChoice


class AvailableExtractModel(StrEnum):
    BASE_OCR_MISTRAL = "base_ocr_mistral"
    # BASE_EXTRACT_PYPDFIUM2 = "base_extract_pypdfium2"


class ExtractSkill(StrEnum):
    EXTRACT_TEXT_FROM_VISUALS = "extract_text_from_visuals"
    EXTARCT_TEXT_FROM_PDF = "extract_text_from_pdf"

    @property
    def model_recommendation(self) -> AvailableExtractModel:
        match self:
            case ExtractSkill.EXTRACT_TEXT_FROM_VISUALS:
                return AvailableExtractModel.BASE_OCR_MISTRAL
            case ExtractSkill.EXTARCT_TEXT_FROM_PDF:
                # TODO: Debug the BaseOcrPypdfium2
                return AvailableExtractModel.BASE_OCR_MISTRAL


class PipeExtractSpec(PipeSpec):
    """Spec for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeExtract enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    Validation Rules:
        - inputs dict must have exactly one input entry, and the value must be either `Image` or `PDF`.
    """

    type: SkipJsonSchema[Literal["PipeExtract"]] = "PipeExtract"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    extract_skill: ExtractSkill | str = Field(description="Select the most adequate extraction model skill according to the task to be performed.")
    page_images: bool | None = Field(default=None, description="Whether to include detected images in the Extract output.")
    page_image_captions: bool | None = Field(default=None, description="Whether to generate captions for detected images using AI.")
    page_views: bool | None = Field(default=None, description="Whether to include rendered page views in the output.")

    @field_validator("extract_skill", mode="before")
    @classmethod
    def validate_extract_skill(cls, extract_skill_value: str) -> ExtractSkill:
        return ExtractSkill(extract_skill_value)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_extract_inputs(cls, inputs_value: dict[str, str] | None) -> dict[str, str] | None:
        if inputs_value is None:
            msg = "PipeExtract must have exactly one input which must be either`Image` or `PDF`."
            raise PipeDefinitionError(msg)
        if len(inputs_value) != 1:
            msg = "PipeExtract must have exactly one input which must be either`Image` or `PDF`."
            raise PipeDefinitionError(msg)
        return inputs_value

    @override
    def to_blueprint(self) -> PipeExtractBlueprint:
        base_blueprint = super().to_blueprint()

        # create extract choice as a str
        extract_model_choice: ExtractModelChoice
        if isinstance(self.extract_skill, ExtractSkill):
            extract_model_choice = self.extract_skill.model_recommendation.value
        else:
            extract_model_choice = ExtractSkill(self.extract_skill).model_recommendation.value

        return PipeExtractBlueprint(
            source=None,
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            model=extract_model_choice,
            page_images=self.page_images,
            page_image_captions=self.page_image_captions,
            page_views=self.page_views,
            page_views_dpi=None,
        )
