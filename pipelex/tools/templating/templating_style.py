from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.tools.templating.text_format import TextFormat


class TagStyle(StrEnum):
    NO_TAG = "no_tag"
    TICKS = "ticks"
    XML = "xml"
    SQUARE_BRACKETS = "square_brackets"


class TemplatingStyle(BaseModel):
    tag_style: TagStyle = Field(strict=False)
    text_format: TextFormat = Field(default=TextFormat.PLAIN, strict=False)

    @override
    def __str__(self):
        return f"{self.tag_style}/{self.text_format}"

    @classmethod
    def make_default_prompting_style(cls) -> Self:
        return cls(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)
