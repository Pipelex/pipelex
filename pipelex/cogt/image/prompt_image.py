import base64
from functools import cached_property
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.filetype_utils import (
    FileType,
    detect_file_type_from_base64,
    detect_file_type_from_bytes,
)
from pipelex.tools.misc.http_utils import URL_MAX_LENGTH
from pipelex.tools.uri.resolved_uri import ResolvedUri
from pipelex.tools.uri.uri_resolver import resolve_uri
from pipelex.types import StrEnum


class PromptImageDetail(StrEnum):
    HIGH = "high"
    LOW = "low"
    AUTO = "auto"

    @property
    def as_openai_detail(self) -> Literal["high", "low", "auto"]:
        return self.value


class PromptImageUri(BaseModel):
    """A prompt image specified by URI (path, URL, storage URI, or data URL)."""

    kind: Literal["uri"] = "uri"
    uri: str

    @field_validator("uri", mode="before")
    @classmethod
    def validate_uri(cls, uri: str) -> str:
        if len(uri) > URL_MAX_LENGTH:
            msg = f"URI is too long: {uri[:100]}..."
            raise ValueError(msg)
        return uri

    @cached_property
    def resolved(self) -> ResolvedUri:
        """Lazily resolve the URI to a typed ResolvedUri."""
        return resolve_uri(self.uri)

    @override
    def __str__(self) -> str:
        truncated_uri = AttributePolisher.get_truncated_value(value=self.uri)
        return f"PromptImageUri(uri={truncated_uri!r})"

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the image."""
        return f"{self.resolved.kind.desc}: {self.uri[:100]}"


class PromptImageBase64(BaseModel):
    """A prompt image as raw base64-encoded bytes."""

    kind: Literal["base64"] = "base64"
    base64_bytes: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.base64_bytes)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    def get_decoded_bytes(self) -> bytes:
        return base64.b64decode(self.base64_bytes)

    @override
    def __str__(self) -> str:
        base64_str = str(self.base64_bytes)
        truncated_base64 = AttributePolisher.get_truncated_value(value=base64_str)
        return f"PromptImageBase64(base64_bytes={truncated_base64!r})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the image."""
        return f"base64: {self.base64_bytes[:100].decode('ascii', errors='replace')}..."


class PromptImageBinary(BaseModel):
    """A prompt image as raw binary bytes."""

    kind: Literal["binary"] = "binary"
    binary_bytes: bytes

    def get_file_type(self) -> FileType:
        return detect_file_type_from_bytes(self.binary_bytes)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    @override
    def __str__(self) -> str:
        return "PromptImageBinary(binary_bytes=...)"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the image."""
        return f"binary: {self.binary_bytes[:50].hex()}..."


PromptImage = Annotated[
    Union[PromptImageUri, PromptImageBase64, PromptImageBinary],
    Field(discriminator="kind"),
]
