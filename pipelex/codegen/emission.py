"""Write a stamped, locked projection to disk — idempotently.

The writing layer sits between an emitter (which produces pure `EmittedFile` bodies) and the filesystem.
For one projection run it: stamps each body (so every file self-describes), writes each file only when
its content changed (no mtime churn — clean diffs, watch-mode friendly), removes any previously-tracked
file that dropped out of the set (so a deleted concept never lingers as a stale generated file), and
rewrites `codegen.lock` with the new artifact set.

Only files the tool itself stamped are ever removed, so a hand-authored file sharing the output
directory is never touched. Input templates (`codegen inputs`) are deliberately *not* stamped or locked:
they are user-editable scaffolds, not tracked generated code.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, build_lock, encode_lock, load_lock
from pipelex.codegen.stamp import apply_stamp, comment_prefix_for, compute_content_hash, has_stamp
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, failable_load_text_from_path, remove_file, save_text_to_path


class WriteReport(BaseModel):
    """What one projection write did to the output tree — for the CLI to report to the user."""

    model_config = ConfigDict(frozen=True)

    written: list[str] = Field(default_factory=list)
    """Artifacts whose content changed and were (re)written."""

    unchanged: list[str] = Field(default_factory=list)
    """Artifacts whose content was already current (skipped — no mtime churn)."""

    removed: list[str] = Field(default_factory=list)
    """Previously-tracked stamped artifacts that dropped out of the set and were deleted."""

    lock_path: str = ""
    """The `codegen.lock` path (relative to the output root)."""


def write_stamped_projection(
    emitted: list[EmittedFile],
    *,
    output_dir: Path,
    crate_fingerprint: str,
    engine_version: str,
    kind: CodegenKind,
    target: CodegenTarget,
    pipe_ref: str | None = None,
    options: dict[str, str] | None = None,
) -> WriteReport:
    """Stamp, write-if-changed, prune de-listed files, and rewrite the lock for one projection run."""
    resolved_options = options or {}
    lock_path = output_dir / CODEGEN_LOCK_FILENAME
    previous_paths = _previous_tracked_paths(lock_path)

    written: list[str] = []
    unchanged: list[str] = []
    artifact_hashes: dict[str, str] = {}

    for emitted_file in emitted:
        stamped = apply_stamp(
            emitted_file.content,
            crate_fingerprint=crate_fingerprint,
            engine_version=engine_version,
            kind=kind,
            target=target,
            pipe_ref=pipe_ref,
            options=resolved_options,
            comment_prefix=comment_prefix_for(emitted_file.filename),
        )
        artifact_hashes[emitted_file.filename] = compute_content_hash(emitted_file.content)
        destination = output_dir / emitted_file.filename
        if _write_if_changed(destination, content=stamped):
            written.append(emitted_file.filename)
        else:
            unchanged.append(emitted_file.filename)

    removed = _prune_delisted(output_dir=output_dir, previous_paths=previous_paths, current_paths=set(artifact_hashes))

    lock = build_lock(crate_fingerprint=crate_fingerprint, engine_version=engine_version, artifacts=artifact_hashes)
    _write_if_changed(lock_path, content=encode_lock(lock))

    return WriteReport(written=written, unchanged=unchanged, removed=removed, lock_path=CODEGEN_LOCK_FILENAME)


def _previous_tracked_paths(lock_path: Path) -> set[str]:
    lock = load_lock(lock_path)
    return lock.paths() if lock is not None else set()


def _write_if_changed(path: Path, *, content: str) -> bool:
    """Write `content` to `path` only if it differs from what is already there. Returns whether it wrote."""
    if failable_load_text_from_path(path) == content:
        return False
    ensure_directory_for_file_path(file_path=path)
    save_text_to_path(text=content, path=path)
    return True


def _prune_delisted(*, output_dir: Path, previous_paths: set[str], current_paths: set[str]) -> list[str]:
    """Delete files that were tracked before but are no longer produced — only if they still carry our stamp."""
    removed: list[str] = []
    for relative in sorted(previous_paths - current_paths):
        stale_path = output_dir / relative
        content = failable_load_text_from_path(stale_path)
        if content is None:
            continue
        if has_stamp(content, comment_prefix=comment_prefix_for(relative)):
            remove_file(stale_path)
            removed.append(relative)
    return removed
