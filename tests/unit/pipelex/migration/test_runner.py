"""Unit tests for the file-level migration runner — backups, per-file scope, and what is written.

The scope is the point. A surface's files are independent user documents, so one that cannot be
processed is reported as blocked while every sibling is migrated normally — unlike the `.mthds`
fix loop, whose files only make sense together and which commits a round all-or-nothing.
"""

import errno
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pytest_mock import MockerFixture

from pipelex.migration.backup import WrittenBackup, existing_backups_of, write_backup
from pipelex.migration.plan import FileBlockedReason
from pipelex.migration.runner import migrate_directories, migrate_file
from pipelex.migration.surfaces import SurfaceRegistry
from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError
from pipelex.pipeline.fixes.file_transaction import FileSnapshot, PendingFileUpdate, commit_file_updates
from pipelex.suggested_fix import RenameTableKeyOp
from tests.unit.pipelex.migration.conftest import EXAMPLE_SURFACE_ID, EntryBuilder, LedgerBuilder, SurfaceBuilder

MOMENT = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)

OLD_SHAPE = """\
[reporting]
output_config = { directory = "out" }
"""


class TestMigrationRunner:
    def test_a_stale_file_is_rewritten_and_backed_up_exactly_once(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert "output = " in target.read_text(encoding="utf-8")
        backups = existing_backups_of(path=target)
        assert backups == [plan.backup_path]
        assert backups[0].read_text(encoding="utf-8") == OLD_SHAPE
        assert backups[0].name == "example.toml.bak.20260815T120000Z"

    def test_a_backup_inherits_the_source_mode_rather_than_the_umask(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """A backup holds the user's values by definition, so a private file must not get a
        world-readable copy sitting beside it.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        target.chmod(0o600)
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.backup_path is not None
        assert stat.S_IMODE(plan.backup_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_an_older_backup_is_pruned_only_after_the_new_file_is_committed(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        stale_backup = tmp_path / "example.toml.bak.20200101T000000Z"
        stale_backup.write_text("from another era\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert not stale_backup.exists()
        assert existing_backups_of(path=target) == [plan.backup_path]

    def test_a_dry_run_writes_nothing_and_backs_nothing_up(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=True, moment=MOMENT)

        assert not plan.was_written
        assert plan.backup_path is None
        assert len(plan.steps) == 1
        assert target.read_text(encoding="utf-8") == OLD_SHAPE
        assert not existing_backups_of(path=target)

    def test_a_current_file_is_neither_written_nor_backed_up(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The overwhelmingly common case under always-replay, and it must cost the user nothing."""
        current = '[reporting]\noutput = { directory = "out" }\n'
        target = tmp_path / "example.toml"
        target.write_text(current, encoding="utf-8")
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.is_clean
        assert not plan.was_written
        assert target.read_text(encoding="utf-8") == current
        assert not existing_backups_of(path=target)

    def test_a_users_own_backup_like_file_survives_the_pruning(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """Only names carrying the stamp we write are ours to prune; anything else beside the file is the user's."""
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        users_own = tmp_path / "example.toml.bak.notes"
        users_own.write_text("my own copy\n", encoding="utf-8")
        stale_backup = tmp_path / "example.toml.bak.20200101T000000Z"
        stale_backup.write_text("from another era\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert users_own.read_text(encoding="utf-8") == "my own copy\n"
        assert not stale_backup.exists()
        assert existing_backups_of(path=target) == [plan.backup_path]

    def test_a_file_name_carrying_a_glob_metacharacter_never_prunes_a_siblings_backup(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """Backups are found by string prefix, not by glob: `example_?.toml` must not see `example_a.toml`'s backups."""
        target = tmp_path / "example_?.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        sibling = tmp_path / "example_a.toml"
        sibling.write_text(OLD_SHAPE, encoding="utf-8")
        siblings_backup = tmp_path / "example_a.toml.bak.20200101T000000Z"
        siblings_backup.write_text("the sibling's only backup\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert siblings_backup.exists()
        assert existing_backups_of(path=target) == [plan.backup_path]
        assert existing_backups_of(path=sibling) == [siblings_backup]

    def test_a_backup_that_cannot_be_placed_leaves_no_staged_copy_behind(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch.object(Path, "replace", side_effect=OSError(errno.EACCES, "Permission denied"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.UNWRITABLE
        assert not plan.was_written
        assert target.read_text(encoding="utf-8") == OLD_SHAPE
        assert sorted(path.name for path in tmp_path.iterdir()) == ["example.toml"]

    def test_a_transaction_error_after_the_write_landed_reports_the_file_as_written(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_surface: SurfaceBuilder,
        write_ledger_file: Callable[..., Path],
    ) -> None:
        """The primitive can raise after the target was replaced (its own temp cleanup failed). The plan must say what happened
        to the file, not what happened to the temp files — and the sibling must still be migrated.
        """
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        first = config_dir / "example.toml"
        first.write_text(OLD_SHAPE, encoding="utf-8")
        second = config_dir / "example_local.toml"
        second.write_text(OLD_SHAPE, encoding="utf-8")
        migration_dir = tmp_path / "migration"
        write_ledger_file(migration_dir=migration_dir, surface_id=EXAMPLE_SURFACE_ID, body=_LEDGER_TOML)
        real_commit = commit_file_updates

        def commit_then_fail_cleanup(updates: list[PendingFileUpdate]) -> None:
            real_commit(updates)
            if updates[0].snapshot.path == first:
                msg = "target changes were committed, but temporary-file cleanup failed"
                raise FixTransactionError(msg)

        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=commit_then_fail_cleanup)

        report = migrate_directories(
            registry=SurfaceRegistry(surfaces=[build_surface()]), migration_dir=migration_dir, config_dirs=[config_dir], dry_run=False, moment=MOMENT
        )

        assert [plan.was_written for plan in report.plans] == [True, True]
        assert all(plan.blocked_reason is None for plan in report.plans)
        assert "output = " in first.read_text(encoding="utf-8")
        assert existing_backups_of(path=first) == [report.plans[0].backup_path]

    def test_a_transaction_error_the_file_denies_reports_an_uncertain_state_and_spares_its_siblings(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_surface: SurfaceBuilder,
        write_ledger_file: Callable[..., Path],
    ) -> None:
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        first = config_dir / "example.toml"
        first.write_text(OLD_SHAPE, encoding="utf-8")
        second = config_dir / "example_local.toml"
        second.write_text(OLD_SHAPE, encoding="utf-8")
        migration_dir = tmp_path / "migration"
        write_ledger_file(migration_dir=migration_dir, surface_id=EXAMPLE_SURFACE_ID, body=_LEDGER_TOML)
        real_commit = commit_file_updates

        def fail_first_commit(updates: list[PendingFileUpdate]) -> None:
            if updates[0].snapshot.path == first:
                msg = "commit failed and rollback was incomplete"
                raise FixTransactionError(msg)
            real_commit(updates)

        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=fail_first_commit)

        report = migrate_directories(
            registry=SurfaceRegistry(surfaces=[build_surface()]), migration_dir=migration_dir, config_dirs=[config_dir], dry_run=False, moment=MOMENT
        )

        assert [plan.was_written for plan in report.plans] == [False, True]
        assert report.plans[0].blocked_reason is FileBlockedReason.STATE_UNCERTAIN
        assert first.read_text(encoding="utf-8") == OLD_SHAPE
        # The transaction could not vouch for the state it left, so the one certain copy of the
        # original stays — under a name outside the `.bak.` rotation, where the next successful
        # run of this file cannot prune it away.
        assert existing_backups_of(path=first) == []
        assert report.plans[0].backup_path is not None
        assert report.plans[0].backup_path.name == "example.toml.rescue.20260815T120000Z"
        assert report.plans[0].backup_path.read_text(encoding="utf-8") == OLD_SHAPE
        assert str(report.plans[0].backup_path) in (report.plans[0].blocked_detail or "")
        assert "output = " in second.read_text(encoding="utf-8")

    def test_an_uncertain_write_does_not_promise_to_keep_a_copy_another_run_made(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """A copy this run did not make stays that run's to move, so it also stays prunable.

        The report may still name it — it does hold the original — but it must not tell the user
        the copy will be waiting, because the next successful run of this file prunes exactly that
        name. What the user needs to be told is to take it now.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        occupied = tmp_path / "example.toml.bak.20260815T120000Z"
        occupied.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=FixTransactionError("commit failed and rollback was incomplete"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.STATE_UNCERTAIN
        assert plan.backup_path == occupied
        assert existing_backups_of(path=target) == [occupied], "still in the rotation, so a later run would prune it"
        detail = plan.blocked_detail or ""
        assert str(occupied) in detail
        assert "is kept at" not in detail
        assert "could not take it out of the way of pruning" in detail

    def test_an_uncertain_write_does_not_promise_a_rescue_the_rename_refused(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The same promise, broken the other way: the copy is this run's, and the rescue name is taken.

        `keep_backup_for_rescue` leaves the copy where it is rather than losing it to a tidier
        name, which is right — and leaves it inside the `.bak.` rotation, which the report must say.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        occupied_rescue = tmp_path / "example.toml.rescue.20260815T120000Z"
        occupied_rescue.write_text("another run got here first\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=FixTransactionError("commit failed and rollback was incomplete"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.STATE_UNCERTAIN
        assert plan.backup_path is not None
        assert plan.backup_path.name == "example.toml.bak.20260815T120000Z"
        assert plan.backup_path.read_text(encoding="utf-8") == OLD_SHAPE
        assert occupied_rescue.read_text(encoding="utf-8") == "another run got here first\n", "never clobbered"
        assert "could not take it out of the way of pruning" in (plan.blocked_detail or "")

    def test_a_file_edited_between_the_read_and_the_write_is_reported_as_changed_and_left_alone(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The snapshot/compare design exists for exactly this: a concurrent edit is never overwritten,
        the user's edit is what stays on disk, and the copy this run made of the pre-edit text goes.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        edited_shape = OLD_SHAPE + "extra = 1\n"
        real_write_backup = write_backup

        def edit_target_while_backing_up(*, snapshot: FileSnapshot, moment: datetime) -> WrittenBackup:
            backup = real_write_backup(snapshot=snapshot, moment=moment)
            target.write_text(edited_shape, encoding="utf-8")
            return backup

        mocker.patch("pipelex.migration.runner.write_backup", side_effect=edit_target_while_backing_up)

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.CHANGED_DURING_RUN
        assert not plan.was_written
        assert target.read_text(encoding="utf-8") == edited_shape
        assert not existing_backups_of(path=target)

    def test_a_write_that_fails_before_touching_the_file_takes_its_backup_with_it(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=OSError(errno.EACCES, "Permission denied"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.UNWRITABLE
        assert not plan.was_written
        assert target.read_text(encoding="utf-8") == OLD_SHAPE
        assert sorted(path.name for path in tmp_path.iterdir()) == ["example.toml"]

    def test_a_backup_that_will_not_go_after_a_refused_write_is_a_warning_not_an_abort(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_surface: SurfaceBuilder,
        write_ledger_file: Callable[..., Path],
    ) -> None:
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        first = config_dir / "example.toml"
        first.write_text(OLD_SHAPE, encoding="utf-8")
        second = config_dir / "example_local.toml"
        second.write_text(OLD_SHAPE, encoding="utf-8")
        migration_dir = tmp_path / "migration"
        write_ledger_file(migration_dir=migration_dir, surface_id=EXAMPLE_SURFACE_ID, body=_LEDGER_TOML)
        real_commit = commit_file_updates

        def refuse_first_commit(updates: list[PendingFileUpdate]) -> None:
            if updates[0].snapshot.path == first:
                raise OSError(errno.EACCES, "Permission denied")
            real_commit(updates)

        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=refuse_first_commit)
        real_unlink = Path.unlink

        def refuse_backup_unlink(self: Path, missing_ok: bool = False) -> None:
            if ".bak." in self.name:
                raise OSError(errno.EPERM, "Operation not permitted")
            real_unlink(self, missing_ok=missing_ok)

        mocker.patch.object(Path, "unlink", refuse_backup_unlink)

        report = migrate_directories(
            registry=SurfaceRegistry(surfaces=[build_surface()]), migration_dir=migration_dir, config_dirs=[config_dir], dry_run=False, moment=MOMENT
        )

        assert [plan.was_written for plan in report.plans] == [False, True]
        assert report.plans[0].blocked_reason is FileBlockedReason.UNWRITABLE
        assert "output = " in second.read_text(encoding="utf-8")

    def test_a_file_that_is_not_utf8_is_blocked_as_unparseable(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_bytes(b"\xff\xfe[reporting]\n")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.UNPARSEABLE
        assert "UTF-8" in (plan.blocked_detail or "")
        assert not existing_backups_of(path=target)

    def test_a_file_that_cannot_be_read_is_blocked_and_nothing_is_written(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch("pipelex.migration.runner.read_file_snapshot", side_effect=PermissionError(errno.EACCES, "Permission denied"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.UNREADABLE
        assert "could not be read" in (plan.blocked_detail or "")
        assert sorted(path.name for path in tmp_path.iterdir()) == ["example.toml"]

    def test_a_file_removed_before_it_is_read_is_reported_as_changed_during_the_run(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.CHANGED_DURING_RUN
        assert not plan.was_written

    def test_a_pruning_failure_never_turns_a_written_file_into_a_blocked_one(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        stale_backup = tmp_path / "example.toml.bak.20200101T000000Z"
        stale_backup.write_text("from another era\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch("pipelex.migration.runner.prune_backups_except", side_effect=OSError(errno.EACCES, "Permission denied"))

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert plan.blocked_reason is None
        assert "output = " in target.read_text(encoding="utf-8")
        assert stale_backup.exists()

    def test_an_unparseable_file_is_blocked_and_its_siblings_are_still_migrated(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
        write_ledger_file: Callable[..., Path],
    ) -> None:
        migration_dir = tmp_path / "migration"
        surface = build_surface()
        ledger = build_ledger(
            entries=[
                build_entry(
                    to_schema_version=2,
                    ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")],
                )
            ]
        )
        write_ledger_file(migration_dir=migration_dir, surface_id=EXAMPLE_SURFACE_ID, body=_LEDGER_TOML)

        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        broken = config_dir / "example.toml"
        broken.write_text("this is not = = toml\n", encoding="utf-8")
        healthy = config_dir / "example_local.toml"
        healthy.write_text(OLD_SHAPE, encoding="utf-8")

        report = migrate_directories(
            registry=SurfaceRegistry(surfaces=[surface]),
            migration_dir=migration_dir,
            config_dirs=[config_dir, tmp_path / "does-not-exist"],
            dry_run=False,
            moment=MOMENT,
        )

        assert len(report.plans) == 2
        blocked_plan = next(plan for plan in report.plans if plan.file_path == broken)
        assert blocked_plan.blocked_reason is FileBlockedReason.UNPARSEABLE
        assert not blocked_plan.was_written
        healthy_plan = next(plan for plan in report.plans if plan.file_path == healthy)
        assert healthy_plan.was_written
        assert "output = " in healthy.read_text(encoding="utf-8")
        assert ledger.surface.current_schema_version == 2

    def test_a_symlinked_configuration_file_migrates_the_file_it_names_and_keeps_the_link(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """A dotfiles setup is a link, and the file the user means is at the end of it.

        An atomic replace of the link path would put a regular file where the link was and leave
        the real file behind, unmigrated — so the runner resolves first, exactly as the `.mthds`
        fix loop already resolves its own targets. The copy lands beside the file it copies.
        """
        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        real = dotfiles / "example.toml"
        real.write_text(OLD_SHAPE, encoding="utf-8")
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        link = config_dir / "example.toml"
        link.symlink_to(real)
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=link, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert link.is_symlink()
        assert link.resolve() == real.resolve()
        assert "output = " in real.read_text(encoding="utf-8")
        # The plan names the path the walk found; the backup shows where the bytes actually went.
        assert plan.file_path == link
        assert plan.backup_path == dotfiles / "example.toml.bak.20260815T120000Z"
        assert not list(existing_backups_of(path=link))

    def test_a_backup_already_at_this_run_s_name_is_kept_rather_than_overwritten(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """Two runs inside one UTC second address the same name, and the older copy is the original.

        The stamp resolves to the second, so a concurrent run of the same file can already have put
        its copy there. Whatever is there is a copy of an *older* state than this run's, so taking
        it away is the one loss backups exist to prevent.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        occupied = tmp_path / "example.toml.bak.20260815T120000Z"
        occupied.write_text("the copy another run already made\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert occupied.read_text(encoding="utf-8") == "the copy another run already made\n"
        assert plan.backup_path == occupied

    def test_a_refused_write_never_discards_a_backup_this_run_did_not_make(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The narrow path the same-second collision actually damages, and the invariant that ends it.

        A run whose commit is refused deletes the copy it made, because a write that did not happen
        has nothing to back up. Deleting the copy it *found* is a different act entirely: that one
        belongs to the run that is presently migrating the file.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        occupied = tmp_path / "example.toml.bak.20260815T120000Z"
        occupied.write_text(OLD_SHAPE, encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )
        mocker.patch(
            "pipelex.migration.runner.commit_file_updates",
            side_effect=FixWriteConflictError("refusing to overwrite: the file changed while changes were being prepared"),
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.blocked_reason is FileBlockedReason.CHANGED_DURING_RUN
        assert occupied.exists()
        assert occupied.read_text(encoding="utf-8") == OLD_SHAPE

    def test_a_rescue_copy_survives_the_next_successful_run_of_the_same_file(
        self,
        tmp_path: Path,
        build_entry: EntryBuilder,
        build_ledger: LedgerBuilder,
        build_surface: SurfaceBuilder,
    ) -> None:
        """The copy a report told the user to go and get must still be there when they go.

        Pruning keeps exactly one `.bak.<stamp>` per file, and a copy kept because a run could not
        say what it had left is not one of those — it is outside the rotation by name, so nothing
        collects it but the user.
        """
        target = tmp_path / "example.toml"
        target.write_text(OLD_SHAPE, encoding="utf-8")
        rescued = tmp_path / "example.toml.rescue.20260101T000000Z"
        rescued.write_text("the original, from a run that could not vouch for its write\n", encoding="utf-8")
        stale_backup = tmp_path / "example.toml.bak.20200101T000000Z"
        stale_backup.write_text("from another era\n", encoding="utf-8")
        ledger = build_ledger(
            entries=[build_entry(to_schema_version=2, ops=[RenameTableKeyOp(table_path=["reporting"], key="output_config", new_key="output")])]
        )

        plan = migrate_file(surface=build_surface(), ledger=ledger, file_path=target, dry_run=False, moment=MOMENT)

        assert plan.was_written
        assert not stale_backup.exists()
        assert rescued.read_text(encoding="utf-8") == "the original, from a run that could not vouch for its write\n"

    def test_a_missing_configuration_directory_is_skipped_rather_than_refused(
        self,
        tmp_path: Path,
        build_surface: SurfaceBuilder,
        write_ledger_file: Callable[..., Path],
    ) -> None:
        migration_dir = tmp_path / "migration"
        write_ledger_file(migration_dir=migration_dir, surface_id=EXAMPLE_SURFACE_ID, body=_LEDGER_TOML)

        report = migrate_directories(
            registry=SurfaceRegistry(surfaces=[build_surface()]),
            migration_dir=migration_dir,
            config_dirs=[tmp_path / "nowhere"],
            dry_run=True,
            moment=MOMENT,
        )

        assert not report.plans


_LEDGER_TOML = """\
[surface]
id = "example-config"
title = "An example configuration surface"
base_file = "example.toml"
tier_glob = "example_*.toml"
current_schema_version = 2
min_supported_schema_version = 0

[[migration]]
id = "example-config@2"
to_schema_version = 2
introduced_in = "0.46.0"
breaking = true
safety = "safe"
title = "Rename the reporting output table"
description = "The reporting output table lost its suffix."

[[migration.ops]]
kind = "rename_table_key"
table_path = ["reporting"]
key = "output_config"
new_key = "output"
"""
