"""Materialize a caller-supplied method bundle into a temporary library directory.

A run request may carry the whole method — the `.mthds` bundle plus its PipeFunc
Python (`pipe_func.py`) and a `requirements.txt` — instead of only
the inline `mthds_contents` text. Two transport forms are accepted, exactly one
per request:

  - `bundle_b64`: a base64-encoded zip archive of the bundle directory.
  - `files`: a `{relative_path: text_content}` map (the zip's contents, unzipped).

The two are equivalent: `files` ≡ the zip's entries. This module decodes either
form, enforces the ingest guards (both transport forms are refused together; a
hard file-count and total-size ceiling; per-entry path-safety against absolute
paths and `..` traversal; a zip-bomb guard that bounds actual decompression),
writes the surviving files into a fresh temp directory, and hands that directory
back so the runner can load it via `library_dirs`. In a sandbox-hosted
deployment the load path reads every `.py` as source text, never importing it:
it refuses a bundle whose Python declares a structure class
(`MethodStructuresRefusedError`, a 403) and captures the rest onto the crate for
the sandbox. The caller is responsible for the hosted-mode gate.

Nothing here imports or executes the bundle's Python — it only writes bytes to
disk. The caller cleans the directory up via the `materialized_bundle` context
manager's guaranteed teardown.
"""

from __future__ import annotations

import base64
import binascii
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NamedTuple

from pipelex import log
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from api.error_types import ErrorType
from api.errors import raise_bad_request, raise_payload_too_large, raise_validation_error
from api.limits import MAX_BUNDLE_FILES, MAX_BUNDLE_TOTAL_BYTES

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True))
class MaterializedBundle:
    """A bundle written to disk: the directory to load and the relpaths written."""

    directory: Path
    relpaths: tuple[str, ...]

    @property
    def has_python_sources(self) -> bool:
        """True when the bundle ships any `.py` — the trigger for the hosted-mode gate."""
        return any(relpath.endswith(".py") for relpath in self.relpaths)


def _safe_relpath(name: str) -> PurePosixPath:
    """Validate one bundle entry name and return it as a normalized relative POSIX path.

    Rejects anything that could escape the destination directory: absolute paths,
    Windows drive/backslash forms (a bare drive prefix like `C:foo` has no slash or
    backslash yet is drive-relative on Windows, so `:` is rejected outright), and any
    `..` component. Directory-only entries (trailing slash) return an empty path and
    are filtered by the caller.
    """
    if not name or name in {".", "./"}:
        return PurePosixPath()
    if "\\" in name:
        msg = f"Bundle entry {name!r} uses backslashes; use forward-slash relative paths only"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    if ":" in name:
        msg = f"Bundle entry {name!r} contains ':' (a Windows drive/stream form); use plain relative paths only"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    pure = PurePosixPath(name)
    if pure.is_absolute():
        msg = f"Bundle entry {name!r} is an absolute path; only relative paths are allowed"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    if any(part == ".." for part in pure.parts):
        msg = f"Bundle entry {name!r} escapes the bundle root via '..'; not allowed"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    return pure


def _guard_count(count: int) -> None:
    if count == 0:
        raise_validation_error(message="Bundle is empty (no files)", error_type=ErrorType.INVALID_BUNDLE)
    if count > MAX_BUNDLE_FILES:
        raise_payload_too_large(message=f"Bundle exceeds the {MAX_BUNDLE_FILES}-file limit (got {count})")


def _guard_running_total(total_bytes: int) -> None:
    if total_bytes > MAX_BUNDLE_TOTAL_BYTES:
        raise_payload_too_large(message=f"Bundle exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB decompressed-size limit")


# Base64 inflates by 4/3; a zip is compressed, so a bundle whose DECOMPRESSED content is within
# the ceiling encodes to well under this. Bounding the base64 string BEFORE decoding stops a
# ~100 MiB request-body (the only other bound) from being expanded into ~75 MiB of heap just to
# be rejected later by the decompressed-size guard. Slack (+4) covers padding.
_MAX_BUNDLE_B64_CHARS = MAX_BUNDLE_TOTAL_BYTES * 4 // 3 + 4


def _entries_from_zip(bundle_b64: str) -> list[tuple[PurePosixPath, bytes]]:
    """Decode a base64 zip and return its (safe relpath, bytes) file entries.

    Zip-bomb guard: each member is read through a bounded stream so a lying
    uncompressed-size header cannot force unbounded decompression — the running
    total is checked against `MAX_BUNDLE_TOTAL_BYTES` as bytes are pulled. A cheap
    length check on the still-encoded string runs FIRST, so an oversized payload is
    refused before it is buffered into memory as decoded bytes.
    """
    if len(bundle_b64) > _MAX_BUNDLE_B64_CHARS:
        raise_payload_too_large(message=f"bundle_b64 exceeds the {MAX_BUNDLE_TOTAL_BYTES // 1024} KiB compressed-size limit")
    try:
        raw = base64.b64decode(bundle_b64, validate=True)
    except (binascii.Error, ValueError) as decode_error:
        log.warning(f"bundle: invalid base64 ({decode_error})")
        raise_bad_request(message="bundle_b64 is not valid base64", error_type=ErrorType.INVALID_BASE64)

    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as zip_error:
        log.warning(f"bundle: corrupt zip ({zip_error})")
        raise_validation_error(message="bundle_b64 is not a valid zip archive", error_type=ErrorType.INVALID_BUNDLE)

    entries: list[tuple[PurePosixPath, bytes]] = []
    total_bytes = 0
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        _guard_count(len(members))
        budget = MAX_BUNDLE_TOTAL_BYTES
        for info in members:
            relpath = _safe_relpath(info.filename)
            if not relpath.parts:
                continue
            # Bounded read: pull at most (remaining budget + 1) bytes so a zip bomb whose header
            # under-reports its size still cannot decompress past the ceiling.
            with archive.open(info) as member:
                data = member.read(budget + 1)
            total_bytes += len(data)
            _guard_running_total(total_bytes)
            budget = MAX_BUNDLE_TOTAL_BYTES - total_bytes
            entries.append((relpath, data))
    return entries


def _entries_from_files(files: dict[str, str]) -> list[tuple[PurePosixPath, bytes]]:
    """Validate a {relpath: text} map and return its (safe relpath, bytes) entries."""
    _guard_count(len(files))
    entries: list[tuple[PurePosixPath, bytes]] = []
    total_bytes = 0
    for name, content in files.items():
        relpath = _safe_relpath(name)
        if not relpath.parts:
            msg = f"Bundle entry {name!r} has no filename"
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
        data = content.encode("utf-8")
        total_bytes += len(data)
        _guard_running_total(total_bytes)
        entries.append((relpath, data))
    return entries


class ParsedBundle(NamedTuple):
    """A decoded-and-validated bundle held in memory, NOT yet written to disk.

    Splitting parse from materialize lets the caller apply the sandbox-hosted gate
    (which keys on `has_python_sources`) BEFORE any disk write — so a bundle destined
    for a 403 never touches the filesystem. Entries are `(safe relpath, bytes)`.
    """

    entries: tuple[tuple[PurePosixPath, bytes], ...]

    @property
    def has_python_sources(self) -> bool:
        """True when the bundle ships any `.py` — the trigger for the hosted-mode gate."""
        return any(str(relpath).endswith(".py") for relpath, _ in self.entries)


def parse_bundle(*, bundle_b64: str | None, files: dict[str, str] | None) -> ParsedBundle:
    """Decode + guard a bundle into an in-memory `ParsedBundle` (no disk writes).

    Exactly one of `bundle_b64` / `files` must be supplied; supplying both is a
    caller mistake (they are the same content in two forms) and is refused. All
    ingest guards (base64, size, count, path-safety, zip-bomb) run here, so the
    caller can inspect `has_python_sources` and reject BEFORE materializing to disk.
    """
    if bundle_b64 is not None and files is not None:
        msg = "Provide either bundle_b64 or files, not both"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    if bundle_b64 is not None:
        entries = _entries_from_zip(bundle_b64)
    elif files is not None:
        entries = _entries_from_files(files)
    else:
        msg = "No bundle supplied (bundle_b64 and files are both absent)"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    return ParsedBundle(entries=tuple(entries))


@contextmanager
def materialize_parsed(parsed: ParsedBundle) -> Generator[MaterializedBundle, None, None]:
    """Write an already-parsed bundle into a fresh temp directory, cleaned up on exit.

    The yielded `MaterializedBundle.directory` is safe to pass as a `library_dirs`
    entry; it is removed when the context exits, on both the happy and error path.
    """
    directory = Path(tempfile.mkdtemp(prefix="pipelex-bundle-"))
    try:
        root = directory.resolve()
        relpaths: list[str] = []
        for relpath, data in parsed.entries:
            target = (directory / relpath).resolve()
            # Defense-in-depth: even after per-part validation, confirm the resolved target stays
            # under the temp root before writing (guards against symlink/edge normalization surprises).
            if root != target and root not in target.parents:
                msg = f"Bundle entry {str(relpath)!r} resolves outside the bundle root"
                raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            relpaths.append(relpath.as_posix())
        yield MaterializedBundle(directory=directory, relpaths=tuple(relpaths))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@contextmanager
def materialized_bundle(*, bundle_b64: str | None, files: dict[str, str] | None) -> Generator[MaterializedBundle, None, None]:
    """Parse AND materialize a bundle in one step (convenience for callers that don't gate).

    Equivalent to `parse_bundle(...)` followed by `materialize_parsed(...)`; a caller
    that must apply the sandbox-hosted gate before disk writes should use the two
    steps directly instead.
    """
    with materialize_parsed(parse_bundle(bundle_b64=bundle_b64, files=files)) as bundle:
        yield bundle
