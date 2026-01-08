"""Prompt document types for passing documents to LLM Workers.

This module defines document types that can be passed to LLM Workers
for document understanding. Follows the same pattern as PromptImage.
"""

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


class PromptDocumentUri(BaseModel):
    """A prompt document specified by URI (path, URL, storage URI, or data URL)."""

    kind: Literal["uri"] = "uri"
    uri: str
    title: str | None = None

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
        title_str = f", title={self.title!r}" if self.title else ""
        return f"PromptDocumentUri(uri={truncated_uri!r}{title_str})"

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        title_part = f" ({self.title})" if self.title else ""
        return f"{self.resolved.kind.desc}: {self.uri[:100]}{title_part}"


class PromptDocumentBase64(BaseModel):
    """A prompt document as base64-encoded string."""

    kind: Literal["base64"] = "base64"
    base64_data: str
    title: str | None = None

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.base64_data)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    def get_decoded_bytes(self) -> bytes:
        return base64.b64decode(self.base64_data)

    @override
    def __str__(self) -> str:
        truncated_base64 = AttributePolisher.get_truncated_value(value=self.base64_data)
        title_str = f", title={self.title!r}" if self.title else ""
        return f"PromptDocumentBase64(base64_data={truncated_base64!r}{title_str})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        title_part = f" ({self.title})" if self.title else ""
        return f"base64: {self.base64_data[:50]}...{title_part}"


class PromptDocumentBinary(BaseModel):
    """A prompt document as raw binary bytes."""

    kind: Literal["binary"] = "binary"
    raw_bytes: bytes
    title: str | None = None

    def get_file_type(self) -> FileType:
        return detect_file_type_from_bytes(self.raw_bytes)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    @override
    def __str__(self) -> str:
        title_str = f", title={self.title!r}" if self.title else ""
        return f"PromptDocumentBinary(raw_bytes=...{title_str})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        title_part = f" ({self.title})" if self.title else ""
        return f"binary: {self.raw_bytes[:50].hex()}...{title_part}"


PromptDocument = Annotated[
    Union[PromptDocumentUri, PromptDocumentBase64, PromptDocumentBinary],
    Field(discriminator="kind"),
]
