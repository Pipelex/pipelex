"""Transactional file replacement — snapshot, stage, atomically replace, roll back on failure.

Extracted from the ``.mthds`` fix loop because configuration migration needs exactly the same
primitives with a different *scope*. The two callers differ in one deliberate way, and it is the
whole reason this module is shared rather than duplicated:

- the ``.mthds`` fix loop commits a whole round **all-or-nothing**: its fixes cascade across files
  of one bundle, and a half-written round leaves a bundle that validates as neither the old shape
  nor the new one;
- a migration commits **one file at a time**, because a surface's files are independent user
  documents. A file that is unparseable, unwritable, or changed during the run is reported as
  blocked while every sibling is migrated and reported normally
  (``docs/migration-ledger.md`` → "Per-file transactions").

Both scopes come out of the same call: ``commit_file_updates`` is all-or-nothing over the list it
is handed, so a list of one *is* the per-file scope.
"""

import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError


class FileSnapshot(NamedTuple):
    """Bytes and identity read from one target before it is replaced."""

    path: Path
    content: bytes
    mode: int
    device: int
    inode: int


class PendingFileUpdate(NamedTuple):
    """A fully rendered replacement paired with the snapshot it was derived from."""

    snapshot: FileSnapshot
    new_content: str


class StagedFileUpdate(NamedTuple):
    """Same-directory temp files for one replacement and its rollback copy."""

    snapshot: FileSnapshot
    replacement_snapshot: FileSnapshot
    rollback_path: Path


def read_file_snapshot(path: Path) -> FileSnapshot:
    """Read bytes and mode from one open file descriptor, avoiding split stat/read state."""
    with path.open("rb") as file:
        content = file.read()
        file_stat = os.fstat(file.fileno())
    return FileSnapshot(
        path=path,
        content=content,
        mode=stat.S_IMODE(file_stat.st_mode),
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
    )


def write_staged_file(*, snapshot: FileSnapshot, content: bytes, label: str) -> Path:
    """Write and fsync a same-directory temp file ready for atomic replacement."""
    temp_file = tempfile.NamedTemporaryFile(  # ruff: ignore[open-file-with-context-handler] - closed before the atomic replace
        mode="wb",
        dir=str(snapshot.path.parent),
        prefix=f".{snapshot.path.name}.pipelex-fix-{label}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(temp_file.name)
    try:
        try:
            temp_file.write(content)
            os.fchmod(temp_file.fileno(), snapshot.mode)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        finally:
            temp_file.close()
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def stage_file_update(update: PendingFileUpdate) -> StagedFileUpdate:
    replacement_path = write_staged_file(snapshot=update.snapshot, content=update.new_content.encode("utf-8"), label="new")
    try:
        replacement_snapshot = read_file_snapshot(replacement_path)
        rollback_path = write_staged_file(snapshot=update.snapshot, content=update.snapshot.content, label="rollback")
    except OSError:
        replacement_path.unlink(missing_ok=True)
        raise
    return StagedFileUpdate(snapshot=update.snapshot, replacement_snapshot=replacement_snapshot, rollback_path=rollback_path)


def file_state_matches(*, current_snapshot: FileSnapshot, expected_snapshot: FileSnapshot) -> bool:
    """Whether content, permissions, and filesystem identity still match an observed file."""
    return (
        current_snapshot.content == expected_snapshot.content
        and current_snapshot.mode == expected_snapshot.mode
        and current_snapshot.device == expected_snapshot.device
        and current_snapshot.inode == expected_snapshot.inode
    )


def assert_snapshot_unchanged(snapshot: FileSnapshot) -> None:
    """Verify that a path still names the exact file state previously observed."""
    try:
        current_snapshot = read_file_snapshot(snapshot.path)
    except FileNotFoundError as exc:
        msg = f"refusing to overwrite '{snapshot.path}': the file was removed while changes were being prepared"
        raise FixWriteConflictError(msg) from exc
    if not file_state_matches(current_snapshot=current_snapshot, expected_snapshot=snapshot):
        msg = f"refusing to overwrite '{snapshot.path}': the file changed while changes were being prepared"
        raise FixWriteConflictError(msg)


def _rollback_committed_updates(committed_updates: list[StagedFileUpdate]) -> list[str]:
    """Restore targets still owned by this transaction, returning rollback failures."""
    failures: list[str] = []
    for staged_update in reversed(committed_updates):
        target_path = staged_update.snapshot.path
        try:
            current_snapshot = read_file_snapshot(target_path)
            if not file_state_matches(current_snapshot=current_snapshot, expected_snapshot=staged_update.replacement_snapshot):
                failures.append(f"{target_path}: file changed after the replacement was committed")
                continue
            staged_update.rollback_path.replace(target_path)
        except OSError as exc:
            failures.append(f"{target_path}: {exc}")
    return failures


def _commit_staged_updates(staged_updates: list[StagedFileUpdate]) -> None:
    committed_updates: list[StagedFileUpdate] = []
    try:
        for staged_update in staged_updates:
            # Accepted portability tradeoff: this check and Path.replace() are not one compare-and-swap operation.
            # An edit in the tiny gap can be overwritten; keep this portable unless real-world evidence justifies serialization.
            assert_snapshot_unchanged(staged_update.snapshot)
            staged_update.replacement_snapshot.path.replace(staged_update.snapshot.path)
            committed_updates.append(staged_update)
    except (FixWriteConflictError, OSError) as exc:
        rollback_failures = _rollback_committed_updates(committed_updates)
        if rollback_failures:
            failures = "; ".join(rollback_failures)
            msg = f"commit failed and rollback was incomplete ({failures}); inspect the named files before retrying"
            raise FixTransactionError(msg) from exc
        raise


def _cleanup_staged_updates(staged_updates: list[StagedFileUpdate]) -> list[str]:
    """Remove transaction temps and record cleanup failures for the caller to report."""
    failures: list[str] = []
    for staged_update in staged_updates:
        for temp_path in (staged_update.replacement_snapshot.path, staged_update.rollback_path):
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"{temp_path}: {exc}")
    return failures


def commit_file_updates(updates: list[PendingFileUpdate]) -> None:
    """Stage every update completely, then atomically replace the targets, rolling back on failure.

    All-or-nothing over the list it is handed. A caller that wants per-file independence calls it
    once per file; a caller whose files only make sense together hands it the whole round.
    """
    staged_updates: list[StagedFileUpdate] = []
    try:
        for update in updates:
            staged_updates.append(stage_file_update(update))
        _commit_staged_updates(staged_updates)
    finally:
        cleanup_failures = _cleanup_staged_updates(staged_updates)
        active_exception = sys.exception()
        if cleanup_failures and active_exception is not None:
            active_exception.add_note(f"temporary-file cleanup also failed ({'; '.join(cleanup_failures)})")
        elif cleanup_failures:
            failures = "; ".join(cleanup_failures)
            msg = f"target changes were committed, but temporary-file cleanup failed ({failures})"
            raise FixTransactionError(msg)
