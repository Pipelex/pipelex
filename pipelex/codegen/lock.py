"""`codegen.lock`: the set-level manifest of generated artifacts (a Pipelex-codegen artifact).

Per-file stamps let a lone file testify about itself; the lock catches the one drift class a stamp
cannot — a **deleted concept whose stale generated file lingers**. It records the generated artifact
*set* (each artifact's path + body content hash) plus the source crate fingerprint and engine version
the set was generated against, so the offline check can spot a file on disk that no longer belongs
(orphan) or a locked file that has vanished (deleted).

`codegen.lock` is Pipelex-owned and distinct from the standard's `methods.lock` (which pins remote
dependency versions): different owner, location, content, and lifecycle — see
`docs/specs/pipelex-codegen.md` → "Lock format". It is encoded as human-diffable TOML, artifacts
sorted by path so version-control diffs stay minimal.
"""
# tomlkit is not fully typed (`tomlkit.dumps`), so its member access reads as unknown here.
# pyright: reportUnknownMemberType=false

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NoReturn
from unicodedata import category

import tomlkit
from pydantic import BaseModel, ConfigDict, Field

from pipelex.codegen.exceptions import CodegenError, CodegenLockError
from pipelex.codegen.stamp import STAMPABLE_SUFFIXES
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.tools.misc.toml_utils import load_toml_from_content
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

CODEGEN_LOCK_FILENAME = "codegen.lock"

_LOCK_HEADER = "# codegen.lock — generated artifact set (Pipelex codegen). Do not edit by hand.\n\n"


class CodegenLockEntry(BaseModel):
    """One tracked artifact: its path relative to the lock, and its body content hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    content_hash: str


class CodegenLock(BaseModel):
    """The generated artifact set for one output root, keyed to the crate + engine it was built against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crate_fingerprint: str
    engine_version: str
    artifacts: list[CodegenLockEntry] = Field(default_factory=empty_list_factory_of(CodegenLockEntry))

    def paths(self) -> set[str]:
        """The set of tracked artifact paths (relative to the lock)."""
        validate_artifact_paths(entry.path for entry in self.artifacts)
        return {entry.path for entry in self.artifacts}

    def hash_by_path(self) -> dict[str, str]:
        """Map each tracked artifact path to its locked body content hash."""
        validate_artifact_paths(entry.path for entry in self.artifacts)
        return {entry.path: entry.content_hash for entry in self.artifacts}


def validate_artifact_path(path: str) -> Path:
    """Validate one canonical artifact path and return its relative filesystem form."""
    if not path:
        _raise_path_error(path, reason="path is empty")
    if "\\" in path:
        _raise_path_error(path, reason="backslashes are not allowed; use forward slashes")
    if any(category(character).startswith("C") for character in path):
        _raise_path_error(path, reason="control characters are not allowed")

    posix_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive or windows_path.root:
        _raise_path_error(path, reason="absolute paths and drive prefixes are not allowed")

    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _raise_path_error(path, reason="empty, '.', and '..' path components are not allowed")

    relative_path = Path(*parts)
    if relative_path.suffix not in STAMPABLE_SUFFIXES:
        expected = ", ".join(sorted(STAMPABLE_SUFFIXES))
        _raise_path_error(path, reason=f"unsupported artifact suffix (expected one of: {expected})")
    return relative_path


def validate_artifact_paths(paths: Iterable[str]) -> dict[str, Path]:
    """Validate an artifact collection and reject duplicate canonical paths."""
    validated: dict[str, Path] = {}
    for path in paths:
        if path in validated:
            _raise_path_error(path, reason="Duplicate artifact path")
        validated[path] = validate_artifact_path(path)
    return validated


def resolve_artifact_path(root: Path, *, artifact_path: str) -> Path:
    """Resolve a validated artifact beneath `root` without following symbolic links."""
    relative_path = validate_artifact_path(artifact_path)
    return resolve_output_path(root, relative_path=relative_path)


def resolve_output_path(root: Path, *, relative_path: Path) -> Path:
    """Resolve one internal output file beneath `root`, rejecting all symlink components."""
    if relative_path.is_absolute() or not relative_path.parts or any(part in {"", ".", ".."} for part in relative_path.parts):
        _raise_path_error(str(relative_path), reason="internal output path must be a canonical relative path")

    normalized_root = Path(os.path.normpath(root.absolute()))
    _reject_symlink_components(normalized_root)
    if normalized_root.exists() and not normalized_root.is_dir():
        _raise_path_error(str(normalized_root), reason="output root exists but is not a directory")

    destination = normalized_root / relative_path
    _reject_symlink_components(destination)
    resolved_root = normalized_root.resolve(strict=False)
    resolved_destination = destination.resolve(strict=False)
    if not resolved_destination.is_relative_to(resolved_root):
        _raise_path_error(str(destination), reason=f"resolved path escapes output root '{resolved_root}'")
    if destination.exists() and not destination.is_file():
        _raise_path_error(str(destination), reason="output destination exists but is not a regular file")
    return destination


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            _raise_path_error(str(path), reason=f"symbolic link component is not allowed: '{current}'")


def _raise_path_error(path: str, *, reason: str) -> NoReturn:
    msg = f"Unsafe codegen artifact path '{path}': {reason}."
    raise CodegenError(msg)


def build_lock(*, crate_fingerprint: str, engine_version: str, artifacts: dict[str, str]) -> CodegenLock:
    """Assemble a lock from a `{path: content_hash}` map, artifacts sorted by path for a stable diff."""
    validate_artifact_paths(artifacts)
    entries = [CodegenLockEntry(path=path, content_hash=content_hash) for path, content_hash in sorted(artifacts.items())]
    return CodegenLock(crate_fingerprint=crate_fingerprint, engine_version=engine_version, artifacts=entries)


def encode_lock(lock: CodegenLock) -> str:
    """Encode the lock as canonical, human-diffable TOML (artifacts already sorted by path)."""
    validate_artifact_paths(entry.path for entry in lock.artifacts)
    payload = {
        "crate_fingerprint": lock.crate_fingerprint,
        "engine_version": lock.engine_version,
        "artifacts": [{"path": entry.path, "content_hash": entry.content_hash} for entry in lock.artifacts],
    }
    return _LOCK_HEADER + tomlkit.dumps(payload)


def load_lock(lock_path: Path) -> CodegenLock | None:
    """Read and parse a `codegen.lock`, or `None` if it does not exist. Raises on a malformed lock."""
    if not lock_path.is_file():
        return None
    try:
        content = load_text_from_path(lock_path)
        data = load_toml_from_content(content)
        lock = CodegenLock.model_validate(data)
        validate_artifact_paths(entry.path for entry in lock.artifacts)
        return lock
    except (CodegenError, TomlError, ValueError, TypeError) as exc:
        # TomlError = malformed TOML; UnicodeDecodeError/ValueError = non-UTF-8 bytes or a pydantic
        # ValidationError on a shape mismatch (UnicodeDecodeError is a ValueError subclass).
        msg = f"Malformed or unsafe codegen lock at '{lock_path}': {exc}"
        raise CodegenLockError(msg) from exc
