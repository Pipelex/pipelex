"""The offline drift check: pure hashing, no engine, no network, no API key.

`codegen check` verifies that generated artifacts still match what the method resolves to — using only
`codegen.lock`, the files on disk, and a hash function. Because it never touches the engine, any client
(this CLI, an SDK, a short CI script) implements it identically, and template improvements never redden
a consumer's CI: regeneration is a dev action, the check is the CI action.

The algorithm (see `docs/specs/pipelex-codegen.md` → "Offline check algorithm"):

1. For each artifact in the lock, locate the file and recompute its body content hash; a mismatch or a
   missing file is a drift.
2. For each generated file present, parse its stamp and recompute the hash below it; a self-inconsistent
   stamp (or a stripped stamp on a locked file) is a hand-edit drift.
3. Detect locked files with no counterpart on disk (deleted) and stamped files not in the lock (orphan).

The verdict rides the structured `CodegenCheckReport`, never the exit code alone — the drifting
artifacts are enumerated by category.
"""

from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, CodegenLock, load_lock
from pipelex.codegen.stamp import STAMPABLE_SUFFIXES, comment_prefix_for, compute_content_hash, has_stamp, parse_stamped
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# Vendor / VCS / cache directories that never hold generated output — pruned from the orphan scan so a
# `codegen check` at a project root does not read (and choke on) unrelated files under them.
_SKIP_DIRS = frozenset(
    {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)


class DriftCategory(StrEnum):
    """The kind of drift found for one artifact."""

    MISSING = "missing"
    """Listed in the lock, absent on disk (a deleted-artifact drift)."""

    MODIFIED = "modified"
    """Present, but its body hash no longer matches the locked hash."""

    HAND_EDITED = "hand-edited"
    """Present, but its stamp is missing or self-inconsistent (edited below the stamp)."""

    ORPHAN = "orphan"
    """A stamped generated file on disk that the lock does not track (a stale lingering artifact)."""


class CodegenDrift(BaseModel):
    """One drifting artifact: its path (relative to the lock), the drift category, and a human detail."""

    model_config = ConfigDict(frozen=True)

    path: str
    category: DriftCategory
    detail: str


class CodegenCheckReport(BaseModel):
    """The structured verdict of an offline check over one output root."""

    model_config = ConfigDict(frozen=True)

    lock_found: bool
    drifts: list[CodegenDrift] = Field(default_factory=empty_list_factory_of(CodegenDrift))

    @property
    def is_current(self) -> bool:
        """Whether generated artifacts are in sync (a lock was found and no drift was detected)."""
        return self.lock_found and not self.drifts


def run_codegen_check(*, root: Path) -> CodegenCheckReport:
    """Run the offline drift check over `root` (the directory holding `codegen.lock`)."""
    lock = load_lock(root / CODEGEN_LOCK_FILENAME)
    if lock is None:
        return CodegenCheckReport(lock_found=False)

    drifts: list[CodegenDrift] = []
    drifts += _check_locked_artifacts(root=root, lock=lock)
    drifts += _find_orphans(root=root, lock=lock)
    return CodegenCheckReport(lock_found=True, drifts=drifts)


def _check_locked_artifacts(*, root: Path, lock: CodegenLock) -> list[CodegenDrift]:
    drifts: list[CodegenDrift] = []
    for path, locked_hash in sorted(lock.hash_by_path().items()):
        file_path = root / path
        if not file_path.is_file():
            drifts.append(CodegenDrift(path=path, category=DriftCategory.MISSING, detail="Locked artifact is absent on disk."))
            continue
        drift = _check_present_artifact(path=path, file_path=file_path, locked_hash=locked_hash)
        if drift is not None:
            drifts.append(drift)
    return drifts


def _check_present_artifact(*, path: str, file_path: Path, locked_hash: str) -> CodegenDrift | None:
    text = _read_text_or_none(file_path)
    if text is None:
        return CodegenDrift(path=path, category=DriftCategory.HAND_EDITED, detail="File is not valid UTF-8 — not generated output.")
    parsed = parse_stamped(text, comment_prefix=comment_prefix_for(path))
    if parsed is None:
        return CodegenDrift(path=path, category=DriftCategory.HAND_EDITED, detail="Stamp header is missing or unparseable.")
    body_hash = compute_content_hash(parsed.body)
    if parsed.stamp.content_hash != body_hash:
        return CodegenDrift(path=path, category=DriftCategory.HAND_EDITED, detail="Body was edited below the stamp (stamp hash no longer matches).")
    if body_hash != locked_hash:
        return CodegenDrift(path=path, category=DriftCategory.MODIFIED, detail="Body no longer matches the locked hash — regenerate.")
    return None


def _find_orphans(*, root: Path, lock: CodegenLock) -> list[CodegenDrift]:
    tracked = lock.paths()
    orphans: list[CodegenDrift] = []
    for file_path in _iter_stampable_files(root):
        relative = file_path.relative_to(root).as_posix()
        if relative in tracked:
            continue
        text = _read_text_or_none(file_path)
        if text is not None and has_stamp(text, comment_prefix=comment_prefix_for(relative)):
            orphans.append(
                CodegenDrift(
                    path=relative,
                    category=DriftCategory.ORPHAN,
                    detail="Stamped generated file not tracked by the lock — stale; remove or regenerate.",
                )
            )
    return orphans


def _iter_stampable_files(directory: Path) -> Iterator[Path]:
    """Yield stampable files under `directory`, pre-order and deterministic, pruning vendor/VCS dirs."""
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            if entry.name not in _SKIP_DIRS:
                yield from _iter_stampable_files(entry)
        elif entry.suffix in STAMPABLE_SUFFIXES:
            yield entry


def _read_text_or_none(path: Path) -> str | None:
    """Read UTF-8 text, or `None` if the file is not valid UTF-8 (so it cannot be our generated output)."""
    try:
        return load_text_from_path(path)
    except UnicodeDecodeError:
        return None
