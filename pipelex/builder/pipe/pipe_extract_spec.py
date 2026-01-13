from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.extract.extract_setting import ExtractModelChoice


class ExtractSkill(StrEnum):
    PDF_TEXT_EXTRACTOR = "pdf_text_extractor"
    IMAGE_TEXT_EXTRACTOR = "image_text_extractor"


class PipeExtractSpec(PipeSpec):
    """Spec for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeExtract enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    Validation Rules:
        - inputs dict must have exactly one input entry, and the value must be either `Image` or `Document` (a PDF is a document).
        - output must be "Page"
    """

    type: SkipJsonSchema[Literal["PipeExtract"]] = "PipeExtract"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    extract_skill: ExtractSkill | str = Field(description="Select the most adequate extraction model skill according to the task to be performed.")
    max_page_images: int | None = Field(
        default=None, description="Max number of images to extract from pages: None=unlimited, 0=no images, N=limit to N images."
    )
    page_image_captions: bool | None = Field(default=None, description="Whether to generate captions for detected images using AI.")
    page_views: bool | None = Field(default=None, description="Whether to include rendered page views in the output.")

    @override
    @field_validator("output", mode="before")
    @classmethod
    def validate_output(cls, output: str) -> str:
        return "Page[]"

    @field_validator("extract_skill", mode="before")
    @classmethod
    def validate_extract_skill(cls, extract_skill_value: str) -> ExtractSkill:
        return ExtractSkill(extract_skill_value)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_extract_inputs(cls, inputs_value: dict[str, str] | None) -> dict[str, str] | None:
        if inputs_value is None:
            msg = "PipeExtract must have exactly one input which must be either `Image` or `Document` (a PDF is a document)."
            raise ValueError(msg)
        if len(inputs_value) != 1:
            msg = "PipeExtract must have exactly one input which must be either `Image` or `Document` (a PDF is a document)."
            raise ValueError(msg)
        return inputs_value

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with extract-specific details
        extract_group = Group()
        extract_group.renderables.append(base_group)

        # Add extract specific information
        extract_group.renderables.append(Text())  # Blank line
        extract_group.renderables.append(Text.from_markup(f"Extract Skill: [bold yellow]{self.extract_skill}[/bold yellow]"))

        # Add optional extraction settings if they are set
        if self.max_page_images is not None:
            extract_group.renderables.append(Text.from_markup(f"Max Page Images: [bold magenta]{self.max_page_images}[/bold magenta]"))
        if self.page_image_captions is not None:
            extract_group.renderables.append(Text.from_markup(f"Generate Image Captions: [bold magenta]{self.page_image_captions}[/bold magenta]"))
        if self.page_views is not None:
            extract_group.renderables.append(Text.from_markup(f"Include Page Views: [bold magenta]{self.page_views}[/bold magenta]"))

        return extract_group

    @override
    def to_blueprint(self) -> PipeExtractBlueprint:
        base_blueprint = super().to_blueprint()

        # create extract choice as a str
        extract_model_choice: ExtractModelChoice = self.extract_skill

        return PipeExtractBlueprint(
            source=None,
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            model=extract_model_choice,
            max_page_images=self.max_page_images,
            page_image_captions=self.page_image_captions,
            page_views=self.page_views,
            page_views_dpi=None,
        )
