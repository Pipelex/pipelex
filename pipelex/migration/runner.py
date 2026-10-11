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

import os
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.exceptions import TOMLKitError

from pipelex import log
from pipelex.fix_ops.exceptions import FixTransactionError, FixWriteConflictError
from pipelex.fix_ops.file_transaction import FileSnapshot, PendingFileUpdate, assert_snapshot_unchanged, commit_file_updates, read_file_snapshot
from pipelex.migration.backup import RescuedBackup, WrittenBackup, keep_backup_for_rescue, prune_backups_except, write_backup
from pipelex.migration.diagnosis import diagnose_unexplained_paths
from pipelex.migration.engine import DocumentReplay, replay_ledger_over_text
from pipelex.migration.ledger import MigrationLedger, load_ledger_cached
from pipelex.migration.plan import FileBlockedReason, MigrationPlan, MigrationReport, UnexplainedPath
from pipelex.migration.surfaces import Surface, SurfaceRegistry
from pipelex.system.configuration.config_surface import version_declared_below_the_floor
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.error_fields import error_fields


def migrate_file(*, surface: Surface, ledger: MigrationLedger, file_path: Path, dry_run: bool, moment: datetime) -> MigrationPlan:
    """Replay one surface's ledger over one file, writing it only when something applied."""
    try:
        # Through a symlink to the file it names, the way the `.mthds` fix loop already resolves its
        # own targets: a configuration file symlinked out of a dotfiles directory is that directory's
        # file, and an atomic replace of the link path would delete the link and leave the real file
        # unmigrated. The plan keeps naming the path the walk found; the backup lands beside the
        # file that was actually rewritten, which is where a copy of it belongs.
        snapshot = read_file_snapshot(file_path.resolve())
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
            reason=FileBlockedReason.UNREADABLE,
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
        document = tomlkit.loads(text)
    except TOMLKitError as exc:
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.UNPARSEABLE,
            # A parse error names a position and a syntax expectation, never a value.
            detail=f"the file is not valid TOML: {exc}",
        )

    below_the_floor = _refuse_a_file_below_the_floor(surface=surface, ledger=ledger, file_path=file_path, document=document)
    if below_the_floor is not None:
        return below_the_floor

    try:
        replay = replay_ledger_over_text(ledger=ledger, text=text)
    except TOMLKitError as exc:
        # The text parsed a moment ago, so this is an operation failing on a document that is
        # valid TOML — an applier bug rather than a bad file. It is reported loudly against the
        # one file it happened on rather than allowed to abort the walk, which is the per-file
        # scope doing its job on a case nobody planned for.
        return _blocked_plan(
            surface_id=surface.surface_id,
            file_path=file_path,
            reason=FileBlockedReason.UNPARSEABLE,
            detail=f"an operation could not be applied to this file: {exc}",
        )

    plan = MigrationPlan(
        surface_id=surface.surface_id,
        file_path=file_path,
        steps=replay.steps,
        blocked=replay.blocked,
        unexplained=_diagnose(surface=surface, ledger=ledger, document=document, replay=replay, text=text),
    )
    if not replay.did_change_document or dry_run:
        return plan
    return _write_migrated_file(plan=plan, snapshot=snapshot, new_content=replay.text, moment=moment)


def _diagnose(*, surface: Surface, ledger: MigrationLedger, document: TOMLDocument, replay: DocumentReplay, text: str) -> list[UnexplainedPath]:
    """Ask what the migration could not explain about the document it is about to leave behind.

    **The document diagnosed is the migrated one**, not the one that was read: everything the
    ledger explains has been carried forward by the time the replay ends, so what is left over is
    genuinely left over. On a dry run that document exists only here, in memory, which is why the
    diagnosis belongs to the run rather than to a later pass over the written file.

    This is where a migration meets the model. The fingerprint is the surface's own projection —
    the same one the coverage gate diffs — and computing it neither loads the user's configuration
    nor touches the network, which is what keeps the command runnable on a machine that cannot
    boot. It costs a walk of the model tree per file, on the order of a couple of milliseconds.
    """
    fingerprint = surface.fingerprint_at(schema_version=ledger.surface.current_schema_version)
    migrated = document if replay.text == text else tomlkit.loads(replay.text)
    return diagnose_unexplained_paths(surface=surface, fingerprint=fingerprint, document=migrated.unwrap(), ledger=ledger, blocked=replay.blocked)


def _refuse_a_file_below_the_floor(*, surface: Surface, ledger: MigrationLedger, file_path: Path, document: TOMLDocument) -> MigrationPlan | None:
    """Refuse a file that declares a schema version this ledger can no longer migrate from.

    The floor is the one thing a replay cannot work out for itself. The applier skips an operation
    whose target is absent and reports success, so a ledger whose oldest entries were squashed
    away would run over a file older than the squash, change nothing, and say it was fine. A
    document that *declares* where it stands is the only evidence available, which is why the
    reserved `[meta] schema_version` is read here — and, through the same predicate, in the
    boot-tolerance retry, which declines the file this refuses.

    Almost every file declares nothing and this returns `None` — the floor is zero on every
    surface today, and nothing writes the key. It earns its place the day a squash moves the floor.
    """
    declared = version_declared_below_the_floor(ledger=ledger, config_dict=document.unwrap())
    if declared is None:
        return None
    floor = ledger.surface.min_supported_schema_version
    return _blocked_plan(
        surface_id=surface.surface_id,
        file_path=file_path,
        reason=FileBlockedReason.UNSUPPORTED_SCHEMA_VERSION,
        detail=(
            f"this file declares schema version {declared} and the '{surface.surface_id}' ledger only migrates from "
            f"version {floor} onwards, so the entries that would bring it forward are no longer there — migrate it "
            f"with a pipelex release that still carries them, or re-create the file"
        ),
    )


class FileWriteOutcome(NamedTuple):
    """What a backed-up write or removal of one file did: where the copy is, whether it landed, and why not.

    The fields a migration plan carries for the file, so a caller reports a write the same way whatever it wrote.
    """

    backup_path: Path | None = None
    was_written: bool = False
    blocked_reason: FileBlockedReason | None = None
    blocked_detail: str | None = None

    def as_plan_update(self) -> dict[str, Any]:
        return {
            "backup_path": self.backup_path,
            "was_written": self.was_written,
            "blocked_reason": self.blocked_reason,
            "blocked_detail": self.blocked_detail,
        }


def _write_migrated_file(*, plan: MigrationPlan, snapshot: FileSnapshot, new_content: str, moment: datetime) -> MigrationPlan:
    """Back the file up and replace it, reporting what happened on the file's plan. See `write_file_with_backup`."""
    outcome = write_file_with_backup(snapshot=snapshot, new_content=new_content, moment=moment)
    return plan.model_copy(update=outcome.as_plan_update())


def write_file_with_backup(*, snapshot: FileSnapshot, new_content: str, moment: datetime) -> FileWriteOutcome:
    """Back the file up, replace it atomically, then prune the older backups.

    The order is the point. Backing up first means there is never a moment with a rewritten file
    and no copy of the original; pruning last means there is never a moment with no backup at all.
    A commit that fails before touching the file takes its own fresh backup with it, so a failed run
    leaves the directory exactly as it found it. The one exception is a commit whose outcome the
    transaction cannot vouch for: then the backup is the only copy whose provenance is certain, and
    it stays, named in the report.

    Nothing raised in here escapes to the caller: this is the per-file boundary, and an exception
    crossing it would abort every sibling file after this one — the one thing the per-file scope
    exists to rule out. Whatever goes wrong lands on the outcome, or, once the file is written, in
    a warning, because a written file is written whatever happens to the housekeeping around it.

    Shared by the ledger replay and the former-release cleanup, so a file either rewrites keeps the
    same one backup and the same guarantees.
    """
    try:
        backup = write_backup(snapshot=snapshot, moment=moment)
    except OSError as exc:
        return FileWriteOutcome(blocked_reason=FileBlockedReason.UNWRITABLE, blocked_detail=f"the backup could not be written: {exc.strerror or exc}")

    try:
        commit_file_updates([PendingFileUpdate(snapshot=snapshot, new_content=new_content)])
    except FixWriteConflictError as exc:
        # The primitive refused before touching the target, so everything this run did is undone by
        # taking back the copy it just made, which has nothing to back up. What the primitive
        # refused *over* is somebody else's write, and `_discard_backup` is what asks whose.
        _discard_backup(backup=backup, snapshot=snapshot, new_content=new_content)
        return FileWriteOutcome(blocked_reason=FileBlockedReason.CHANGED_DURING_RUN, blocked_detail=str(exc))
    except OSError as exc:
        _discard_backup(backup=backup, snapshot=snapshot, new_content=new_content)
        return FileWriteOutcome(blocked_reason=FileBlockedReason.UNWRITABLE, blocked_detail=f"the file could not be written: {exc.strerror or exc}")
    except FixTransactionError as exc:
        # For the single-file commit this runner performs, a replace that fails re-raises its own
        # `OSError` or `FixWriteConflictError` — a rollback of nothing is trivially complete — so
        # the only `FixTransactionError` that reaches here is the one raised *after* the target was
        # replaced, when the temporary files could not be removed. The write landed; whether it is
        # still what landed is the open question, and the file answers it.
        if not _carries(path=snapshot.path, content=new_content):
            kept = _keep_the_original(backup=backup, path=snapshot.path, moment=moment)
            return FileWriteOutcome(
                blocked_reason=FileBlockedReason.STATE_UNCERTAIN,
                blocked_detail=(
                    f"the write could not be confirmed: the file does not hold what this run wrote, and the transaction could not "
                    f"say what it left behind — {_whereabouts_of(kept=kept)}: {exc}"
                ),
                backup_path=kept.path,
            )
        log.warning(
            "A configuration file was migrated, but the write left temporary files behind",
            fields={OTelLogAttr.FILE_PATH: str(snapshot.path), **error_fields(exc=exc)},
        )

    _prune_older_backups(snapshot=snapshot, backup=backup)
    return FileWriteOutcome(backup_path=backup.path, was_written=True)


def remove_file_with_backup(*, snapshot: FileSnapshot, moment: datetime) -> FileWriteOutcome:
    """Back the file up, remove it, then prune the older backups — the removal twin of `write_file_with_backup`.

    The copy is taken first and kept, so a removed file is one rename away from being back. The file is removed only
    if it is still exactly what was read: a file changed or removed in between is someone else's work, reported and
    left alone. The copy this run took of a file still on disk is taken back; the copy of a file that is gone stays,
    since a concurrent run may have removed it after adopting that copy as its own (`_discard_created_backup`). The
    path itself is removed, so a symbolic link goes and the file it names, someone's dotfiles, stays.

    Like the write, nothing raised here crosses the per-file boundary.
    """
    try:
        backup = write_backup(snapshot=snapshot, moment=moment)
    except OSError as exc:
        return FileWriteOutcome(blocked_reason=FileBlockedReason.UNWRITABLE, blocked_detail=f"the backup could not be written: {exc.strerror or exc}")

    try:
        assert_snapshot_unchanged(snapshot)
        snapshot.path.unlink()
    except FixWriteConflictError as exc:
        kept = _discard_created_backup(backup=backup, snapshot=snapshot)
        return FileWriteOutcome(blocked_reason=FileBlockedReason.CHANGED_DURING_RUN, blocked_detail=str(exc), backup_path=kept)
    except FileNotFoundError:
        kept = _discard_created_backup(backup=backup, snapshot=snapshot)
        return FileWriteOutcome(
            blocked_reason=FileBlockedReason.CHANGED_DURING_RUN,
            blocked_detail="the file was removed while the cleanup was running",
            backup_path=kept,
        )
    except OSError as exc:
        kept = _discard_created_backup(backup=backup, snapshot=snapshot)
        return FileWriteOutcome(
            blocked_reason=FileBlockedReason.UNWRITABLE, blocked_detail=f"the file could not be removed: {exc.strerror or exc}", backup_path=kept
        )

    _prune_older_backups(snapshot=snapshot, backup=backup)
    return FileWriteOutcome(backup_path=backup.path, was_written=True)


def _prune_older_backups(*, snapshot: FileSnapshot, backup: WrittenBackup) -> None:
    try:
        prune_backups_except(path=snapshot.path, keep=backup.path)
    except OSError as exc:
        # An older backup that would not go is a housekeeping failure on a file that is already
        # migrated and already backed up. Not the plan's to report as a failure of the file.
        log.warning(
            "An older backup of a configuration file could not be pruned",
            fields={OTelLogAttr.FILE_PATH: str(snapshot.path), "backup_path": str(backup.path), **error_fields(exc=exc, text=exc.strerror)},
        )


def _discard_created_backup(*, backup: WrittenBackup, snapshot: FileSnapshot) -> Path | None:
    """Remove the copy this run made of a file it then did not remove, unless it may be the last copy of that file.

    The removal's `_discard_backup`, asking the file the same question. Another run's copy is that run's, and stays. A
    file still on disk was not removed by anyone — a user edited it, or it would not go — so this run's copy backs
    up nothing and goes. A file no longer on disk may have been removed by a concurrent run of the same second, which
    found this copy's name taken and adopted it as its own: that copy is then the only one of the file anywhere, named
    by a report that is already out, so it stays.

    Returns:
        The copy that stays and is worth naming, or `None` when there is none.
    """
    if not backup.was_created:
        return None
    if not os.path.lexists(snapshot.path):
        return backup.path
    try:
        backup.path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning(
            "A backup made for a removal that did not happen could not be removed",
            fields={OTelLogAttr.FILE_PATH: str(snapshot.path), "backup_path": str(backup.path), **error_fields(exc=exc, text=exc.strerror)},
        )
    return None


def _keep_the_original(*, backup: WrittenBackup, path: Path, moment: datetime) -> RescuedBackup:
    """Take this run's backup out of the rotation, so the next successful run cannot prune it.

    Only a copy this run made: another run's backup of the same file is that run's to name and to
    move, and renaming it here would make its report point at a file that no longer exists. That
    copy holds the original all the same, so it is still what the report names — as a copy still in
    the rotation, which is what `was_rescued` says.
    """
    if not backup.was_created:
        return RescuedBackup(path=backup.path, was_rescued=False)
    return keep_backup_for_rescue(path=path, backup_path=backup.path, moment=moment)


def _whereabouts_of(*, kept: RescuedBackup) -> str:
    """How to tell the user where the one certain copy of their file is, and how long it will be there.

    A copy that left the `.bak.` rotation is safe until the user removes it, and the report says so.
    One that could not be moved is a copy the next successful run of this file will prune, so the
    report asks for the one thing that saves it — taking it now.
    """
    if kept.was_rescued:
        return f"the copy taken before the migration is kept at '{kept.path}'"
    return (
        f"a copy of the file as it was is at '{kept.path}', and this run could not take it out of the way of pruning — "
        f"copy it aside before the next successful run of this file"
    )


def _discard_backup(*, backup: WrittenBackup, snapshot: FileSnapshot, new_content: str) -> None:
    """Remove the copy this run made of a file it then did not rewrite.

    Only the copy this run made. A backup already sitting at that name belongs to a concurrent run
    of the same file, and it is a copy of an older state — the original, if anything is; deleting
    it here would destroy the one thing backups exist for on the way to reporting a write that
    never happened.

    And only while nobody else has done this run's work. The stamp resolves to the second, so a
    concurrent run of the same file that found this name taken adopted it as *its* restore point
    without writing anything there. If that run has since committed, the file already holds the
    text this run was going to write — and the copy under this name is the last of the original,
    named by a report that is already out. So the file is asked what it holds rather than assumed
    to be as it was: only this run's own text acquits the other run of having got there first.

    A user's edit is the other reason a write is refused, and it is not this: the file then holds
    the user's text, the copy goes as it always did, and nothing is left beside a file they did not
    ask to have backed up.

    A copy that will not go is a stray file beside an untouched original — worth a warning, never
    worth an exception crossing the per-file boundary and aborting the siblings.
    """
    if not backup.was_created or _carries(path=snapshot.path, content=new_content):
        return
    try:
        backup.path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning(
            "A backup made for a write that did not happen could not be removed",
            fields={OTelLogAttr.FILE_PATH: str(snapshot.path), "backup_path": str(backup.path), **error_fields(exc=exc, text=exc.strerror)},
        )


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
    only_surface_id: str | None = None,
    skipped_paths: Collection[Path] = (),
    moment: datetime | None = None,
) -> MigrationReport:
    """Migrate every claimed file in every given configuration directory.

    The walk is over the directories a caller names — in practice the global `~/.pipelex/` and the
    project's `.pipelex/`, and only those. A directory that does not exist is skipped.

    `skipped_paths` are files the walk leaves out altogether: the ones the former-release cleanup
    removes, which `pipelex migrate` runs first. A file about to be deleted is neither counted among
    the files to migrate nor reported as needing a look, in the rehearsal or in the write pass.

    `only_surface_id` narrows the answer to one surface, for a caller that is diagnosing a
    particular model's refusal rather than migrating the machine. **It narrows the result, not the
    registry, and that distinction is the whole point**: which surface owns a file is decided
    across *all* of them — an exact base file claims before any glob — so a registry holding one
    surface could hand another surface's base file to its glob and replay the wrong ledger over
    it. Arbitration first, then the filter.
    """
    stamp = moment if moment is not None else datetime.now(UTC)
    skipped = {_walk_identity(path=path) for path in skipped_paths}
    plans: list[MigrationPlan] = []
    for directory in config_dirs:
        for surface, file_path in registry.files_by_surface_in_directory(directory=directory):
            if only_surface_id is not None and surface.surface_id != only_surface_id:
                continue
            if _walk_identity(path=file_path) in skipped:
                continue
            ledger = load_ledger_cached(migration_dir=migration_dir, surface_id=surface.surface_id)
            plans.append(migrate_file(surface=surface, ledger=ledger, file_path=file_path, dry_run=dry_run, moment=stamp))
    return MigrationReport(plans=plans)


def _walk_identity(*, path: Path) -> Path:
    """A file as the walk compares it: its directory resolved and its own name kept, so a link is the link itself."""
    return path.parent.resolve() / path.name
