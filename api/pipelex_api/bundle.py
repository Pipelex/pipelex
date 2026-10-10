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
back so the runner can load it via `library_dirs`.

A bundle may also ship the method packages it calls by address, each under
`.mthds/methods/<name>/` at its root with its `METHODS.toml` there, the layout the
standard names the local method cache. `partition_bundle_entries` sorts the entries
into the bundle's own `.mthds` files, its other files, and those packages, refusing
every other `.mthds` path with a `422 InvalidBundle` naming the entry, and two
packages declaring the same address with one naming both directories, and
`materialized_methods_dir` writes the packages into a temp directory of their own,
`<tmp>/<name>/…`, which the runner hands the engine as `methods_dirs`. In a sandbox-hosted
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
from typing import TYPE_CHECKING, NamedTuple, NoReturn

from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.exceptions import ManifestError
from mthds.package.manifest.parser import parse_methods_toml
from pipelex import log
from pipelex.tools.log.error_fields import error_fields
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_payload_too_large, raise_validation_error
from pipelex_api.limits import MAX_BUNDLE_FILES, MAX_BUNDLE_TOTAL_BYTES

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
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle's base64 could not be decoded", fields=error_fields(exc=decode_error))
        raise_bad_request(message="bundle_b64 is not valid base64", error_type=ErrorType.INVALID_BASE64)

    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as zip_error:
        # DEBUG: the refusal below is a caller's mistake, which the error handler already logs; this keeps the cause.
        log.debug("A bundle is not a valid zip archive", fields=error_fields(exc=zip_error))
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
    r"""Validate a {relpath: text} map and return its (safe relpath, bytes) entries.

    JSON can carry a lone surrogate as an escape (`"\ud800"`), which has no UTF-8 form, so an entry whose name or
    content holds one is refused with a `422` naming it rather than failing later, when it is encoded or written.
    """
    _guard_count(len(files))
    entries: list[tuple[PurePosixPath, bytes]] = []
    total_bytes = 0
    for name, content in files.items():
        try:
            name.encode("utf-8")
        except UnicodeEncodeError:
            msg = f"Bundle entry {name!r} has a name holding a lone surrogate, which is not valid Unicode text"
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
        relpath = _safe_relpath(name)
        if not relpath.parts:
            msg = f"Bundle entry {name!r} has no filename"
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
        try:
            data = content.encode("utf-8")
        except UnicodeEncodeError:
            msg = f"Bundle entry {name!r} holds a lone surrogate, which is not valid Unicode text"
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
        total_bytes += len(data)
        _guard_running_total(total_bytes)
        entries.append((relpath, data))
    return entries


def _refuse_colliding_paths(entries: list[tuple[PurePosixPath, bytes]]) -> None:
    """Refuse two entries of one path, and an entry that is also the directory of another.

    Entry names are normalized (`a/./b` and `a//b` are `a/b`) and a zip may hold one member name twice, so two entries
    can name one file: a check reading the first copy, as the shipped packages' manifest check does, would pass content
    that differs from the last copy, which is the one written to disk and read by the engine. A file that another entry
    is placed under could not be written at all.
    """
    paths: set[PurePosixPath] = set()
    for relpath, _ in entries:
        if relpath in paths:
            msg = f"Bundle has more than one entry for the path '{relpath.as_posix()}'; each file may appear only once"
            raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
        paths.add(relpath)
    for relpath, _ in entries:
        for parent in relpath.parents:
            if parent in paths:
                msg = f"Bundle entry '{parent.as_posix()}' is a file, and also the directory of the entry '{relpath.as_posix()}'"
                raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)


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
    ingest guards (base64, size, count, path-safety, zip-bomb, colliding paths) run
    here, so the caller can inspect `has_python_sources` and reject BEFORE
    materializing to disk.
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
    _refuse_colliding_paths(entries)
    return ParsedBundle(entries=tuple(entries))


# Where a bundle ships the method packages it calls: `.mthds/methods/<name>/`, at the bundle's root and nowhere else.
_MTHDS_DIR_NAME = ".mthds"
_METHODS_DIR_NAME = "methods"
_VENDORING_LAYOUT = (
    "A method package shipped with the bundle goes under '.mthds/methods/<name>/' at the bundle's root, "
    "with its manifest at '.mthds/methods/<name>/METHODS.toml'."
)


class VendoredMethodPackage(NamedTuple):
    """A method package a bundle ships under `.mthds/methods/<name>/`, held in memory."""

    name: str
    """The package's directory name under `.mthds/methods/`."""

    full_address: str
    """The address its manifest declares, `address/name`, as a reference names it and a refusal names the package."""

    entries: tuple[tuple[PurePosixPath, bytes], ...]
    """Every file of the package, by its path relative to the package directory."""


class BundlePartition(NamedTuple):
    """A bundle's entries sorted into its own `.mthds` files, its other files, and the packages it ships."""

    mthds_entries: tuple[tuple[PurePosixPath, bytes], ...]
    library_entries: tuple[tuple[PurePosixPath, bytes], ...]
    vendored_packages: tuple[VendoredMethodPackage, ...]


def _refuse_entry(*, owner: str, relpath: PurePosixPath, reason: str) -> NoReturn:
    msg = f"{owner} entry '{relpath.as_posix()}' {reason}. {_VENDORING_LAYOUT}"
    raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)


def _vendored_package(*, owner: str, name: str, entries: list[tuple[PurePosixPath, bytes]]) -> VendoredMethodPackage:
    """Check one shipped package's directory and read the address its manifest declares."""
    package_label = f"'.mthds/methods/{name}/'"
    if name.startswith("."):
        msg = f"{owner} ships {package_label}, a hidden directory, which is never searched for a package. {_VENDORING_LAYOUT}"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    manifest_bytes = next((data for relpath, data in entries if relpath == PurePosixPath(MANIFEST_FILENAME)), None)
    if manifest_bytes is None:
        msg = f"{owner} ships {package_label} without a {MANIFEST_FILENAME}, so no reference could find it. {_VENDORING_LAYOUT}"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    manifest_path = f".mthds/methods/{name}/{MANIFEST_FILENAME}"
    try:
        manifest = parse_methods_toml(manifest_bytes.decode("utf-8"))
    except UnicodeDecodeError:
        msg = f"{owner} entry '{manifest_path}' is not valid UTF-8. {_VENDORING_LAYOUT}"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    except ManifestError as exc:
        msg = f"{owner} entry '{manifest_path}' is not a valid method package manifest: {exc.message} {_VENDORING_LAYOUT}"
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)
    # The name a reference matches, as the engine's discovery gives it: the manifest's, else the directory's.
    package_name = manifest.name if manifest.name is not None else name
    return VendoredMethodPackage(name=name, full_address=f"{manifest.address}/{package_name}", entries=tuple(entries))


def _refuse_shared_identities(*, owner: str, packages: tuple[VendoredMethodPackage, ...]) -> None:
    """Refuse shipped packages a reference could not tell apart, rather than let the directory order pick one.

    A reference is matched against a package's full address without regard to case, as the engine's lookup compares it,
    so two packages whose full addresses differ only in case are one identity too.
    """
    by_identity: dict[str, list[VendoredMethodPackage]] = {}
    for package in packages:
        by_identity.setdefault(package.full_address.casefold(), []).append(package)
    for sharing in by_identity.values():
        if len(sharing) < 2:
            continue
        directories = ", ".join(f"'.mthds/methods/{package.name}/'" for package in sharing)
        msg = (
            f"{owner} ships several method packages declaring the address '{sharing[0].full_address}': {directories}. "
            "A reference matches a package by its address without regard to case, so it could not tell them apart: "
            "ship one package per address."
        )
        raise_validation_error(message=msg, error_type=ErrorType.INVALID_BUNDLE)


def partition_bundle_entries(entries: tuple[tuple[PurePosixPath, bytes], ...], *, owner: str = "Bundle") -> BundlePartition:
    """Sort a bundle's entries into its own `.mthds` files, its other files, and the method packages it ships.

    An entry under `.mthds/methods/<name>/`, whatever its extension, belongs to the shipped package `<name>`, which
    leaves the bundle's own content and its library directory. Every other `.mthds` path component is refused with a
    `422 InvalidBundle` naming the entry rather than dropped, since nothing could ever find what it holds: a file
    elsewhere under `.mthds/`, a `.mthds/methods/` store below the root, a file directly under `.mthds/methods/`, and a
    `.mthds/` inside a shipped package, whose own dependencies are not loaded. A shipped package must be a directory
    whose name does not start with a dot and whose `METHODS.toml` parses, and the address that manifest declares is read
    here, to name the package in a refusal. Two shipped packages declaring the same full address, compared without regard
    to case as a reference is matched, are refused too, naming the address and both directories, since nothing but their
    directory order would decide which one answers. Counting the bundle's own `.mthds` files is the caller's: a bundle
    whose only `.mthds` files are shipped ones has no content of its own.

    Args:
        entries: The bundle's `(safe relpath, bytes)` entries.
        owner: How a refusal names the bundle, for a method package fetched by address as for a request's bundle.

    Returns:
        The three groups, each in the bundle's entry order.
    """
    mthds_entries: list[tuple[PurePosixPath, bytes]] = []
    library_entries: list[tuple[PurePosixPath, bytes]] = []
    vendored_entries: dict[str, list[tuple[PurePosixPath, bytes]]] = {}
    for relpath, data in entries:
        parts = relpath.parts
        if parts[0] == _MTHDS_DIR_NAME:
            if len(parts) < 4 or parts[1] != _METHODS_DIR_NAME:
                _refuse_entry(owner=owner, relpath=relpath, reason="is under '.mthds/' but not inside a shipped method package")
            package_relpath = PurePosixPath(*parts[3:])
            if _MTHDS_DIR_NAME in package_relpath.parts:
                _refuse_entry(
                    owner=owner,
                    relpath=relpath,
                    reason="is a '.mthds/' directory inside a shipped method package, whose own dependencies are not loaded",
                )
            vendored_entries.setdefault(parts[2], []).append((package_relpath, data))
        elif _MTHDS_DIR_NAME in parts:
            _refuse_entry(owner=owner, relpath=relpath, reason="is under a '.mthds/' directory below the bundle's root, which is never searched")
        elif relpath.suffix == ".mthds":
            mthds_entries.append((relpath, data))
        else:
            library_entries.append((relpath, data))
    vendored_packages = tuple(
        _vendored_package(owner=owner, name=name, entries=package_entries) for name, package_entries in vendored_entries.items()
    )
    _refuse_shared_identities(owner=owner, packages=vendored_packages)
    return BundlePartition(mthds_entries=tuple(mthds_entries), library_entries=tuple(library_entries), vendored_packages=vendored_packages)


@contextmanager
def materialize_parsed(parsed: ParsedBundle, *, prefix: str = "pipelex-bundle-") -> Generator[MaterializedBundle, None, None]:
    """Write an already-parsed bundle into a fresh temp directory, cleaned up on exit.

    The yielded `MaterializedBundle.directory` is safe to pass as a `library_dirs`
    entry; it is removed when the context exits, on both the happy and error path.
    """
    directory = Path(tempfile.mkdtemp(prefix=prefix))
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
def materialized_methods_dir(packages: tuple[VendoredMethodPackage, ...]) -> Generator[Path, None, None]:
    """Write shipped method packages into a temp directory of their own, as `<tmp>/<name>/…`, cleaned up on exit.

    The directory is laid out like `.mthds/methods/`, one directory per package, which is what the engine's
    `methods_dirs` take, and its path holds no `.mthds/methods` a walk-up from a bundle could take for a store.
    """
    entries = tuple((PurePosixPath(package.name) / relpath, data) for package in packages for relpath, data in package.entries)
    with materialize_parsed(ParsedBundle(entries=entries), prefix="pipelex-methods-") as materialized:
        yield materialized.directory


@contextmanager
def materialized_bundle(*, bundle_b64: str | None, files: dict[str, str] | None) -> Generator[MaterializedBundle, None, None]:
    """Parse AND materialize a bundle in one step (convenience for callers that don't gate).

    Equivalent to `parse_bundle(...)` followed by `materialize_parsed(...)`; a caller
    that must apply the sandbox-hosted gate before disk writes should use the two
    steps directly instead.
    """
    with materialize_parsed(parse_bundle(bundle_b64=bundle_b64, files=files)) as bundle:
        yield bundle
