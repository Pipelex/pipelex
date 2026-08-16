"""Running a migration over real files — read, replay, back up, write, report.

The scope here is **per file**, and that is the difference from the `.mthds` fix loop this code
shares its transaction primitives with. A bundle's files only make sense together, so that loop
commits a round all-or-nothing; a surface's files are independent user documents, so a file that
is unparseable, unwritable or changed during the run is reported as blocked while every sibling is
migrated and reported normally.

Nothing here decides *whether* to migrate. There is no version resolution and no state stamp: the
engine replays the whole ledger over every file and the applier skips whatever is already done.

See `docs/migration-ledger.md` → "Applying" and "Per-file transactions".
"""

from datetime import UTC, datetime
from pathlib import Path

from tomlkit.exceptions import TOMLKitError

from pipelex import log
from pipelex.migration.backup import prune_backups_except, write_backup
from pipelex.migration.engine import replay_ledger_over_text
from pipelex.migration.ledger import MigrationLedger, load_ledger_cached
from pipelex.migration.plan import FileBlockedReason, MigrationPlan, MigrationReport
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError
from pipelex.pipeline.fixes.file_transaction import FileSnapshot, PendingFileUpdate, commit_file_updates, read_file_snapshot


def migrate_file(*, surface: Surface, ledger: MigrationLedger, file_path: Path, dry_run: bool, moment: datetime) -> MigrationPlan:
    """Replay one surface's ledger over one file, writing it only when something applied."""
    try:
        snapshot = read_file_snapshot(file_path)
    except FileNotFoundError:
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.CHANGED_DURING_RUN,
            detail="the file was removed while the migration was being prepared",
        )
    except OSError as exc:
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.UNWRITABLE,
            detail=f"the file could not be read: {exc.strerror or exc}",
        )

    try:
        text = snapshot.content.decode("utf-8")
    except UnicodeDecodeError:
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.UNPARSEABLE,
            detail="the file is not valid UTF-8",
        )

    try:
        replay = replay_ledger_over_text(ledger=ledger, text=text)
    except TOMLKitError as exc:
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.UNPARSEABLE,
            # A parse error names a position and a syntax expectation, never a value.
            detail=f"the file is not valid TOML: {exc}",
        )

    plan = MigrationPlan(
        surface_id=surface.surface_id,
        file_path=file_path,
        steps=replay.steps,
        blocked=replay.blocked,
    )
    if not replay.did_change_document or dry_run:
        return plan
    return _write_migrated_file(plan=plan, snapshot=snapshot, new_content=replay.text, moment=moment)


def _write_migrated_file(*, plan: MigrationPlan, snapshot: FileSnapshot, new_content: str, moment: datetime) -> MigrationPlan:
    """Back the file up, replace it atomically, then prune the older backups.

    The order is the point. Backing up first means there is never a moment with a rewritten file
    and no copy of the original; pruning last means there is never a moment with no backup at all.
    A commit that fails takes its own fresh backup with it, so a failed run leaves the directory
    exactly as it found it.

    Nothing raised in here escapes to the caller: this is the per-file boundary, and an exception
    crossing it would abort every sibling file after this one — the one thing the per-file scope
    exists to rule out. Whatever goes wrong lands on this file's plan, or, once the file is
    written, in a warning, because a written file is written whatever happens to the housekeeping
    around it.
    """
    try:
        backup_path = write_backup(snapshot=snapshot, moment=moment)
    except OSError as exc:
        return plan.model_copy(
            update={
                "blocked_reason": FileBlockedReason.UNWRITABLE,
                "blocked_detail": f"the backup could not be written: {exc.strerror or exc}",
            }
        )

    try:
        commit_file_updates([PendingFileUpdate(snapshot=snapshot, new_content=new_content)])
    except FixWriteConflictError as exc:
        backup_path.unlink(missing_ok=True)
        return plan.model_copy(update={"blocked_reason": FileBlockedReason.CHANGED_DURING_RUN, "blocked_detail": str(exc)})
    except OSError as exc:
        backup_path.unlink(missing_ok=True)
        return plan.model_copy(
            update={"blocked_reason": FileBlockedReason.UNWRITABLE, "blocked_detail": f"the file could not be written: {exc.strerror or exc}"}
        )
    except FixTransactionError as exc:
        # The primitive raises this when it cannot vouch for the state it leaves behind — a rollback
        # that did not complete, or a replacement that landed but whose temp files could not be
        # removed. The exception cannot say which; the file can, so ask it.
        if not _carries(path=snapshot.path, content=new_content):
            backup_path.unlink(missing_ok=True)
            return plan.model_copy(update={"blocked_reason": FileBlockedReason.UNWRITABLE, "blocked_detail": f"the file could not be written: {exc}"})
        log.warning(f"'{snapshot.path}' was migrated, but the write left something behind: {exc}")

    try:
        prune_backups_except(path=snapshot.path, keep=backup_path)
    except OSError as exc:
        # An older backup that would not go is a housekeeping failure on a file that is already
        # migrated and already backed up. Not the plan's to report as a failure of the file.
        log.warning(
            f"'{snapshot.path}' was migrated and backed up to '{backup_path}', but an older backup could not be pruned: {exc.strerror or exc}"
        )
    return plan.model_copy(update={"backup_path": backup_path, "was_written": True})


def _carries(*, path: Path, content: str) -> bool:
    """Whether the file on disk holds exactly this text — the one question a failed commit leaves open."""
    try:
        return path.read_bytes() == content.encode("utf-8")
    except OSError:
        return False


def _blocked_plan(*, surface_id: str, file_path: Path, reason: FileBlockedReason, detail: str) -> MigrationPlan:
    return MigrationPlan(surface_id=surface_id, file_path=file_path, blocked_reason=reason, blocked_detail=detail)


def migrate_directories(
    *,
    registry: SurfaceRegistry,
    migration_dir: Path,
    config_dirs: list[Path],
    dry_run: bool,
    moment: datetime | None = None,
) -> MigrationReport:
    """Migrate every claimed file in every given configuration directory.

    The walk is over the directories a caller names — in practice the global `~/.pipelex/` and the
    project's `.pipelex/`, and only those. A directory that does not exist is skipped.
    """
    stamp = moment if moment is not None else datetime.now(UTC)
    plans: list[MigrationPlan] = []
    for directory in config_dirs:
        for surface, file_path in registry.files_by_surface_in_directory(directory=directory):
            ledger = load_ledger_cached(migration_dir=migration_dir, surface_id=surface.surface_id)
            plans.append(migrate_file(surface=surface, ledger=ledger, file_path=file_path, dry_run=dry_run, moment=stamp))
    return MigrationReport(plans=plans)
