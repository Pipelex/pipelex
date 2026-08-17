from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex.tools.templating.text_format import TextFormat


class TagStyle(StrEnum):
    NO_TAG = "no_tag"
    TICKS = "ticks"
    XML = "xml"
    SQUARE_BRACKETS = "square_brackets"


class TemplatingStyle(BaseModel):
    """How a pipe's inputs are tagged and formatted into its prompt: a tag style and a text format."""

    # An authored surface: a misspelled key must fail validation, not silently yield a different prompt shape.
    model_config = ConfigDict(extra="forbid")

    tag_style: TagStyle = Field(strict=False)
    text_format: TextFormat = Field(default=TextFormat.PLAIN, strict=False)

    @override
    def __str__(self):
        return f"{self.tag_style}/{self.text_format}"
