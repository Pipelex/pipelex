# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field
from typing_extensions import override


class TextFormat(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    SPREADSHEET = "spreadsheet"

    @property
    def render_method_name(self):
        return f"rendered_{self}"


class TagStyle(StrEnum):
    NO_TAG = "no_tag"
    TICKS = "ticks"
    XML = "xml"
    SQUARE_BRACKETS = "square_brackets"


class PromptingStyle(BaseModel):
    tag_style: TagStyle = Field(strict=False)
    text_format: TextFormat = Field(TextFormat.PLAIN, strict=False)

    @override
    def __str__(self):
        return f"{self.tag_style}/{self.text_format}"

    @classmethod
    def make_default_prompting_style(cls) -> Self:
        return cls(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)
