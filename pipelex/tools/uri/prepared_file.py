"""Prepared files ready to be used by various components.

This module defines the output of file preparation - files in a format
that can be directly consumed by different APIs (either as HTTP URLs,
local paths, or as base64-encoded data with mime type).
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from pipelex.tools.misc.base64_utils import make_base64_url
from pipelex.tools.misc.filetype_utils import FileType


class PreparedFileHttpUrl(BaseModel):
    """An HTTP URL that can be passed directly to APIs that accept URLs."""

    kind: Literal["http_url"] = "http_url"
    url: str


class PreparedFileLocalPath(BaseModel):
    """A local file path for direct file system access."""

    kind: Literal["local_path"] = "local_path"
    path: str


class PreparedFileBase64(BaseModel):
    """Base64-encoded file data with mime type."""

    kind: Literal["base64"] = "base64"
    base64_data: str
    file_type: FileType

    @property
    def mime_type(self) -> str:
        """Return the MIME type of the file."""
        return self.file_type.mime

    def as_data_url(self) -> str:
        """Convert to a data: URL for APIs that accept it."""
        return make_base64_url(base64_data=self.base64_data, file_type=self.file_type)


PreparedFile = Annotated[
    Union[PreparedFileHttpUrl, PreparedFileLocalPath, PreparedFileBase64],
    Field(discriminator="kind"),
]
