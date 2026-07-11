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
from pipelex.codegen.exceptions import CodegenError, CodegenLockError
from pipelex.codegen.lock import (
    CODEGEN_LOCK_FILENAME,
    CodegenLock,
    build_lock,
    encode_lock,
    load_lock,
    resolve_artifact_path,
    resolve_output_path,
    validate_artifact_paths,
)
from pipelex.codegen.stamp import apply_stamp, comment_prefix_for, compute_content_hash, has_stamp, parse_stamped
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, failable_load_text_from_path, remove_file, save_text_to_path
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class StampedProjection(BaseModel):
    """One projection's stamped artifact set plus its lock — pure content, no filesystem.

    This is the single source of truth for what a projection *is* on disk: `write_stamped_projection`
    materializes it locally, and a serving host (the HTTP codegen route) returns it over the wire —
    so a client that writes `files` and `lock_content` verbatim produces byte-identical artifacts
    and passes the offline `codegen check` exactly as a local run would.
    """

    model_config = ConfigDict(frozen=True)

    files: list[EmittedFile] = Field(default_factory=empty_list_factory_of(EmittedFile))
    """The emitted files with their stamp headers applied (same filenames, stamped contents)."""

    lock: CodegenLock
    """The artifact-set lock (paths + body hashes + crate fingerprint + engine version)."""

    lock_content: str
    """The lock encoded as canonical TOML — written verbatim as `codegen.lock`."""


def build_stamped_projection(
    emitted: list[EmittedFile],
    *,
    crate_fingerprint: str,
    engine_version: str,
    kind: CodegenKind,
    target: CodegenTarget,
    pipe_ref: str | None = None,
    options: dict[str, str] | None = None,
) -> StampedProjection:
    """Stamp each emitted body and assemble the matching lock — pure, no filesystem access."""
    validate_artifact_paths(emitted_file.filename for emitted_file in emitted)
    resolved_options = options or {}
    stamped_files: list[EmittedFile] = []
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
        stamped_files.append(EmittedFile(filename=emitted_file.filename, content=stamped))
        artifact_hashes[emitted_file.filename] = compute_content_hash(emitted_file.content)
    lock = build_lock(crate_fingerprint=crate_fingerprint, engine_version=engine_version, artifacts=artifact_hashes)
    return StampedProjection(files=stamped_files, lock=lock, lock_content=encode_lock(lock))


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
    lock_path = resolve_output_path(output_dir, relative_path=Path(CODEGEN_LOCK_FILENAME))
    output_root = lock_path.parent
    previous_paths = _previous_tracked_paths(lock_path)

    projection = build_stamped_projection(
        emitted,
        crate_fingerprint=crate_fingerprint,
        engine_version=engine_version,
        kind=kind,
        target=target,
        pipe_ref=pipe_ref,
        options=options,
    )
    _preflight_destinations(output_root=output_root, projection=projection, previous_paths=previous_paths)

    written: list[str] = []
    unchanged: list[str] = []
    for stamped_file in projection.files:
        destination = resolve_artifact_path(output_root, artifact_path=stamped_file.filename)
        if _write_if_changed(destination, content=stamped_file.content):
            written.append(stamped_file.filename)
        else:
            unchanged.append(stamped_file.filename)

    removed = _prune_delisted(output_dir=output_root, previous_paths=previous_paths, current_paths=projection.lock.paths())

    _write_if_changed(lock_path, content=projection.lock_content)

    return WriteReport(written=written, unchanged=unchanged, removed=removed, lock_path=CODEGEN_LOCK_FILENAME)


def _preflight_destinations(*, output_root: Path, projection: StampedProjection, previous_paths: set[str]) -> None:
    """Reject unowned destination collisions before any projection file is written."""
    for stamped_file in projection.files:
        destination = resolve_artifact_path(output_root, artifact_path=stamped_file.filename)
        existing_content = failable_load_text_from_path(destination)
        if existing_content is None or existing_content == stamped_file.content:
            continue
        if stamped_file.filename in previous_paths:
            continue
        comment_prefix = comment_prefix_for(stamped_file.filename)
        if parse_stamped(existing_content, comment_prefix=comment_prefix) is not None:
            continue
        msg = f"Refusing to overwrite unowned file '{destination}'. Move it or choose a different codegen output directory."
        raise CodegenError(msg)


def _previous_tracked_paths(lock_path: Path) -> set[str]:
    try:
        lock = load_lock(lock_path)
    except CodegenLockError as exc:
        if isinstance(exc.__cause__, CodegenError):
            # Unsafe tracked paths are not corrupt state to overwrite: they are a security
            # violation, and suppressing them would weaken the containment boundary.
            raise
        # A new projection is authoritative and can replace a corrupt prior lock. Without a
        # trustworthy artifact set there is nothing safe to prune, so recover with an empty set.
        return set()
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
        stale_path = resolve_artifact_path(output_dir, artifact_path=relative)
        content = failable_load_text_from_path(stale_path)
        if content is None:
            continue
        if has_stamp(content, comment_prefix=comment_prefix_for(relative)):
            remove_file(stale_path)
            removed.append(relative)
    return removed
