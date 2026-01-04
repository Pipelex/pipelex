"""Prepared images ready to be sent to LLM APIs.

This module defines the output of image preparation - images in a format
that can be directly consumed by LLM provider APIs (either as HTTP URLs
or as base64-encoded data with mime type).
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from pipelex.tools.misc.base64_utils import make_base64_url
from pipelex.tools.misc.filetype_utils import FileType


class PreparedImageHttpUrl(BaseModel):
    """An HTTP URL that can be passed directly to some LLMs."""

    kind: Literal["http_url"] = "http_url"
    url: str


class PreparedImageBase64(BaseModel):
    """Base64-encoded image data with mime type."""

    kind: Literal["base64"] = "base64"
    base64_bytes: bytes
    file_type: FileType

    @property
    def mime_type(self) -> str:
        """Return the MIME type of the image."""
        return self.file_type.mime

    def as_data_url(self) -> str:
        """Convert to a data: URL for APIs that accept it."""
        return make_base64_url(base64_bytes=self.base64_bytes, file_type=self.file_type)


PreparedImage = Annotated[
    Union[PreparedImageHttpUrl, PreparedImageBase64],
    Field(discriminator="kind"),
]
