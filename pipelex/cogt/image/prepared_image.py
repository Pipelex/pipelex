"""Prepared images ready to be sent to LLM APIs.

This module defines the output of image preparation - images in a format
that can be directly consumed by LLM provider APIs (either as HTTP URLs
or as base64-encoded data with mime type).
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from pipelex.tools.misc.filetype_utils import FileType


class PreparedImageUrl(BaseModel):
    """An HTTP URL that can be passed directly to the LLM."""

    kind: Literal["url"] = "url"
    url: str


class PreparedImageData(BaseModel):
    """Base64-encoded image data with mime type."""

    kind: Literal["data"] = "data"
    base_64: bytes
    file_type: FileType

    @property
    def mime_type(self) -> str:
        """Return the MIME type of the image."""
        return self.file_type.mime

    def as_data_url(self) -> str:
        """Convert to a data: URL for APIs that accept it."""
        return f"data:{self.mime_type};base64,{self.base_64.decode('utf-8')}"


PreparedImage = Annotated[
    Union[PreparedImageUrl, PreparedImageData],
    Field(discriminator="kind"),
]
