from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.exceptions import PipeDefinitionError
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.ocr.ocr_setting import OcrChoice


class AvailableOcr(StrEnum):
    BASE_OCR_MISTRAL = "base_ocr_mistral"
    # BASE_OCR_PYPDFIUM2 = "base_ocr_pypdfium2"


class OcrSkill(StrEnum):
    EXTRACT_TEXT_FROM_VISUALS = "extract_text_from_visuals"
    EXTARCT_TEXT_FROM_PDF = "extract_text_from_pdf"

    @property
    def ocr_recommendation(self) -> AvailableOcr:
        match self:
            case OcrSkill.EXTRACT_TEXT_FROM_VISUALS:
                return AvailableOcr.BASE_OCR_MISTRAL
            case OcrSkill.EXTARCT_TEXT_FROM_PDF:
                # TODO: Debug the BaseOcrPypdfium2
                return AvailableOcr.BASE_OCR_MISTRAL


class PipeOcrSpec(PipeSpec):
    """Spec for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeOcr enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    Validation Rules:
        - inputs dict must have exactly one input entry, and the value must be either `Image` or `PDF`.
    """

    type: SkipJsonSchema[Literal["PipeOcr"]] = "PipeOcr"
    category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    ocr: OcrSkill | str = Field(description="Use one of the recommended OCR choices")
    page_images: bool | None = Field(default=None, description="Whether to include detected images in the OCR output.")
    page_image_captions: bool | None = Field(default=None, description="Whether to generate captions for detected images using AI.")
    page_views: bool | None = Field(default=None, description="Whether to include rendered page views in the output.")

    @field_validator("ocr", mode="before")
    @classmethod
    def validate_ocr(cls, ocr_value: str) -> OcrSkill:
        return OcrSkill(ocr_value)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_ocr_inputs(cls, inputs_value: dict[str, str] | None) -> dict[str, str] | None:
        if inputs_value is None:
            msg = "PipeOcr must have exactly one input which must be either`Image` or `PDF`."
            raise PipeDefinitionError(msg)
        if len(inputs_value) != 1:
            msg = "PipeOcr must have exactly one input which must be either`Image` or `PDF`."
            raise PipeDefinitionError(msg)
        return inputs_value

    @override
    def to_blueprint(self) -> PipeOcrBlueprint:
        base_blueprint = super().to_blueprint()

        # create ocr choice as a str
        ocr: OcrChoice
        if isinstance(self.ocr, OcrSkill):
            ocr = self.ocr.ocr_recommendation.value
        else:
            ocr = OcrSkill(self.ocr).ocr_recommendation.value

        return PipeOcrBlueprint(
            source=None,
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            ocr=ocr,
            page_images=self.page_images,
            page_image_captions=self.page_image_captions,
            page_views=self.page_views,
            page_views_dpi=None,
        )
