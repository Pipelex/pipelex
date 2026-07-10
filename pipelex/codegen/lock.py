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

from pathlib import Path

import tomlkit
from pydantic import BaseModel, ConfigDict, Field

from pipelex.codegen.exceptions import CodegenLockError
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.file_utils import failable_load_text_from_path
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
        return {entry.path for entry in self.artifacts}

    def hash_by_path(self) -> dict[str, str]:
        """Map each tracked artifact path to its locked body content hash."""
        return {entry.path: entry.content_hash for entry in self.artifacts}


def build_lock(*, crate_fingerprint: str, engine_version: str, artifacts: dict[str, str]) -> CodegenLock:
    """Assemble a lock from a `{path: content_hash}` map, artifacts sorted by path for a stable diff."""
    entries = [CodegenLockEntry(path=path, content_hash=content_hash) for path, content_hash in sorted(artifacts.items())]
    return CodegenLock(crate_fingerprint=crate_fingerprint, engine_version=engine_version, artifacts=entries)


def encode_lock(lock: CodegenLock) -> str:
    """Encode the lock as canonical, human-diffable TOML (artifacts already sorted by path)."""
    payload = {
        "crate_fingerprint": lock.crate_fingerprint,
        "engine_version": lock.engine_version,
        "artifacts": [{"path": entry.path, "content_hash": entry.content_hash} for entry in lock.artifacts],
    }
    return _LOCK_HEADER + tomlkit.dumps(payload)


def load_lock(lock_path: Path) -> CodegenLock | None:
    """Read and parse a `codegen.lock`, or `None` if it does not exist. Raises on a malformed lock."""
    content = failable_load_text_from_path(lock_path)
    if content is None:
        return None
    try:
        data = load_toml_from_content(content)
        return CodegenLock.model_validate(data)
    except (TomlError, ValueError, TypeError) as exc:
        # TomlError = malformed TOML; ValueError = pydantic ValidationError on a shape mismatch.
        msg = f"Malformed codegen lock at '{lock_path}': {exc}"
        raise CodegenLockError(msg) from exc
