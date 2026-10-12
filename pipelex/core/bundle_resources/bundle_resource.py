"""A bundle's resources: the files beside its `.mthds` text that its steps read, such as a `PipeDocGen` template file.

A bundle loaded from a directory finds them beside its file on disk. A bundle submitted as content strings, which is
how the runner's routes receive one, has no directory, so the files come with it: each is keyed by the
bundle-relative path a step names, read as if every bundle of the submission sat in one directory. The library holds
them for its pipes to read, and its crate carries them wherever the library is loaded again.

A resource carries its bytes inline, base64-encoded so that it serializes to JSON like the rest of a crate, or by
reference to the run's storage. A file a step reads when the method loads, such as an HTML template, which is checked
against the step's inputs, always travels inline, like the bundle's own text, so the files read at load are bounded in
total (`MAX_LOAD_STAGE_RESOURCES_BYTES`). A file a step reads only when it runs, such as an office template, which only
its engine opens, moves to the run's storage before a run is handed to an orchestrator outside this process, so a run
that crosses to another process carries a reference rather than the bytes.
"""

import base64
import binascii
import hashlib
from collections.abc import Mapping
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.core.bundle_resources.exceptions import BundleResourceError, BundleResourcePathError
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract

MAX_LOAD_STAGE_RESOURCES_BYTES = 512 * 1024
"""The most the files a bundle's steps read when the method loads, such as its HTML templates, may total, in bytes.

They travel inline in the method's crate wherever it runs, a remote orchestrator's payloads included, where the remote
side reads them while it loads the crate and may do no IO, so they cannot move to the run's storage as an office
template does. Sized well under Temporal's 2 MB payload limit, with room for the third that base64 adds and for the
method's own text. A fixed bound, not a setting: raising it would let a run that passed every check fail at dispatch.
"""


class BundleResourceReadStage(StrEnum):
    """When a step reads a file of its bundle, which decides how the file travels with the bundle's crate."""

    LOAD = "load"
    """Read while the method loads, such as an HTML template checked against the step's inputs: it travels inline."""

    RUN = "run"
    """Read only when the step runs, such as an office template its engine fills: it may travel by reference."""


def _path_refusal(*, path: str) -> str | None:
    """Why `path` cannot name a file inside a bundle, or None when it can."""
    if not path.strip():
        return "it is empty"
    if "\\" in path:
        return "it holds a backslash; write the path with forward slashes"
    if ":" in path:
        return "it holds a colon"
    if "\x00" in path:
        return "it holds a NUL character"
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute():
        return "it is absolute; write it relative to the bundle"
    if ".." in pure_path.parts:
        return "it leaves the bundle through a '..' segment"
    if not pure_path.parts:
        return "it names no file"
    return None


def canonical_resource_path_or_none(*, path: str) -> str | None:
    """The one spelling of a bundle-relative path, or None when it cannot name a file inside the bundle.

    `.` segments and repeated slashes collapse, so `./invoice.xlsx` and `invoice.xlsx` name one file.
    """
    if _path_refusal(path=path) is not None:
        return None
    return PurePosixPath(path).as_posix()


def canonical_resource_path(*, path: str) -> str:
    """The one spelling of a bundle-relative path, the key a resource is held and looked up under.

    POSIX separators only, relative, and inside the bundle: an absolute path, a `..` segment, a backslash, a colon
    and an empty path are refused. `.` segments and repeated slashes collapse, so `./invoice.xlsx` and
    `invoice.xlsx` name one file.

    Raises:
        BundleResourcePathError: the path cannot name a file inside the bundle.
    """
    refusal = _path_refusal(path=path)
    if refusal is not None:
        msg = f"The file '{path}' submitted with the bundle cannot be one of its files: {refusal}."
        raise BundleResourcePathError(msg)
    return PurePosixPath(path).as_posix()


class BundleResource(BaseModel):
    """One file of a bundle, with its bytes inline or stored, and their digest either way."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(description="The SHA-256 of the file's bytes, in hexadecimal")
    size: int = Field(ge=0, description="The file's size in bytes")
    content_b64: str | None = Field(default=None, description="The file's bytes, base64-encoded, when they travel inline")
    uri: str | None = Field(default=None, description="The pipelex-storage URI of the file's bytes, when they were stored")

    @model_validator(mode="after")
    def validate_carrier(self) -> Self:
        if (self.content_b64 is None) == (self.uri is None):
            msg = "A bundle resource carries its bytes either inline or by reference, exactly one of the two."
            raise ValueError(msg)
        if self.uri is not None and not self.uri.startswith(PIPELEX_STORAGE_SCHEME):
            msg = f"A bundle resource stored by reference names a '{PIPELEX_STORAGE_SCHEME}' URI."
            raise ValueError(msg)
        return self

    @classmethod
    def make_inline(cls, *, content: bytes) -> Self:
        return cls(
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
            content_b64=base64.b64encode(content).decode("ascii"),
        )

    def stored_at(self, *, uri: str) -> Self:
        """The same file, now carried by reference to where its bytes were stored."""
        return self.model_copy(update={"content_b64": None, "uri": uri})

    @property
    def is_inline(self) -> bool:
        return self.content_b64 is not None

    def inline_bytes(self) -> bytes:
        """The file's bytes, which it carries inline.

        Raises:
            BundleResourceError: the file was stored, so its bytes are read through the run's storage.
        """
        if self.content_b64 is None:
            msg = "The bundle file was stored with its run, so it is read through the run's storage provider."
            raise BundleResourceError(msg)
        try:
            return base64.b64decode(self.content_b64, validate=True)
        except binascii.Error as exc:
            msg = "The bundle file's inline bytes are not valid base64."
            raise BundleResourceError(msg) from exc

    async def read_bytes(self, *, storage_provider: StorageProviderAbstract) -> bytes:
        """The file's bytes, inline or read back from storage and checked against their digest.

        A stored file is read from its own `pipelex-storage://` URI only. The caller authorizes that read against the
        run's read scope first, as it does every file a step reads.

        Raises:
            BundleResourceError: the stored bytes no longer match the digest the file was submitted with.
        """
        if self.content_b64 is not None:
            return self.inline_bytes()
        if self.uri is None:
            msg = "A bundle resource carries its bytes either inline or by reference."
            raise BundleResourceError(msg)
        data = await storage_provider.load(self.uri)
        if hashlib.sha256(data).hexdigest() != self.sha256:
            msg = "The stored bundle file no longer matches the file submitted with the bundle."
            raise BundleResourceError(msg)
        return data


BundleResources = dict[str, BundleResource]
"""A bundle's files, keyed by their canonical bundle-relative path."""


def make_bundle_resources(*, files: Mapping[str, bytes]) -> BundleResources:
    """The files submitted with a bundle, keyed by their canonical path and carried inline.

    Raises:
        BundleResourcePathError: a path cannot name a file inside the bundle, or two paths name the same file.
    """
    resources: BundleResources = {}
    for path, content in files.items():
        canonical_path = canonical_resource_path(path=path)
        if canonical_path in resources:
            msg = f"Two files submitted with the bundle name the same file '{canonical_path}'."
            raise BundleResourcePathError(msg)
        resources[canonical_path] = BundleResource.make_inline(content=content)
    return resources
