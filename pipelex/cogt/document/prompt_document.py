"""Prompt document types for passing documents to LLM Workers.

This module defines document types that can be passed to LLM Workers
for document understanding. Follows the same pattern as PromptImage.
"""

import base64
import binascii
from functools import cached_property
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.filetype_utils import (
    FILE_HEAD_NB_BYTES,
    UNKNOWN_FILE_TYPE,
    FileType,
    detect_file_type_from_base64,
    detect_file_type_from_bytes,
    identify_mime_type,
    mime_type_to_extension,
)
from pipelex.tools.misc.hash_utils import hash_sha256
from pipelex.tools.misc.http_utils import URL_MAX_LENGTH
from pipelex.tools.uri.resolved_uri import ResolvedUri
from pipelex.tools.uri.uri_resolver import resolve_uri


class PromptDocumentUri(BaseModel):
    """A prompt document specified by URI (path, URL, storage URI, or data URL)."""

    kind: Literal["uri"] = "uri"
    uri: str
    mime_type: str | None = None

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
        return f"PromptDocumentUri(uri={truncated_uri!r})"

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        return f"{self.resolved.kind.desc}: {self.uri[:100]}"

    def get_document_type(self) -> str:
        """Get the document type (extension) from stored mime_type.

        Returns:
            File extension (e.g., "pdf", "docx") or UNKNOWN_FILE_TYPE if mime_type is not set.
        """
        if self.mime_type:
            return mime_type_to_extension(self.mime_type)
        return UNKNOWN_FILE_TYPE

    def known_mime_type(self) -> str | None:
        """The MIME type this document is known to have, without loading it: the one run setup stamped, if any."""
        return self.mime_type

    def get_content_hash(self, *, length: int | None = None) -> str:
        """Return a hash of the document content."""
        return hash_sha256(self.uri, length=length)


class PromptDocumentBase64(BaseModel):
    """A prompt document as base64-encoded string."""

    kind: Literal["base64"] = "base64"
    base64_data: str
    mime_type: str | None = None
    """The type run setup established or the data URL declared, which refines what the bytes alone identify."""

    def get_file_type(self) -> FileType:
        return detect_file_type_from_base64(self.base64_data)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    def get_decoded_bytes(self) -> bytes:
        return base64.b64decode(self.base64_data)

    def known_mime_type(self) -> str | None:
        """The MIME type this document is known to have, identified the way run setup identifies it.

        The bytes win when they identify a type, the declared type stands when they identify none or
        do not decode, and a declared zip-based type refines bytes that show only a zip.
        """
        try:
            raw_bytes = self.get_decoded_bytes()
        except binascii.Error:
            return self.mime_type
        return identify_mime_type(head=raw_bytes[:FILE_HEAD_NB_BYTES], declared_mime_type=self.mime_type, file_name=None)

    @override
    def __str__(self) -> str:
        truncated_base64 = AttributePolisher.get_truncated_value(value=self.base64_data)
        return f"PromptDocumentBase64(base64_data={truncated_base64!r})"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __format__(self, format_spec: str) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        return f"base64: {self.base64_data[:50]}..."

    def get_document_type(self) -> str:
        """Get the document type (extension) from the file contents."""
        return self.get_file_type().extension

    def get_content_hash(self, *, length: int | None = None) -> str:
        """Return a hash of the document content."""
        return hash_sha256(self.base64_data, length=length)


class PromptDocumentBinary(BaseModel):
    """A prompt document as raw binary bytes."""

    kind: Literal["binary"] = "binary"
    raw_bytes: bytes
    mime_type: str | None = None
    """The type the caller declared, which refines what the bytes alone identify."""

    def get_file_type(self) -> FileType:
        return detect_file_type_from_bytes(self.raw_bytes)

    def get_mime_type(self) -> str:
        return self.get_file_type().mime

    def known_mime_type(self) -> str | None:
        """The MIME type this document is known to have, identified the way run setup identifies it."""
        return identify_mime_type(head=self.raw_bytes[:FILE_HEAD_NB_BYTES], declared_mime_type=self.mime_type, file_name=None)

    @override
    def __str__(self) -> str:
        return "PromptDocumentBinary(raw_bytes=...)"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    def short_description(self) -> str:
        """Return a short description of the document."""
        return f"binary: {self.raw_bytes[:50].hex()}..."

    def get_document_type(self) -> str:
        """Get the document type (extension) from the file contents."""
        return self.get_file_type().extension

    def get_content_hash(self, *, length: int | None = None) -> str:
        """Return a hash of the document content."""
        return hash_sha256(self.raw_bytes, length=length)


PromptDocument = Annotated[
    Union[PromptDocumentUri, PromptDocumentBase64, PromptDocumentBinary],
    Field(discriminator="kind"),
]
