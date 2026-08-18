"""Unit tests for the `.gitignore` pipelex keeps inside the configuration directory it owns.

The rule under test is narrow on purpose: a backup is pipelex's own transient copy and has no
business in a user's `git status`, while a `.rescue.` copy exists precisely because a write could
not be vouched for — turning up in `git status` is how the user finds out it is there.
"""

from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path

from pipelex.cli.commands.init.config_files import init_config
from pipelex.migration.backup import backup_path_for, rescue_path_for
from pipelex.migration.gitignore import (
    BACKUP_IGNORE_PATTERN,
    CONFIG_DIR_GITIGNORE_NAME,
    ensure_config_dir_gitignore,
)
from pipelex.migration.run import migrate_config_directories

MOMENT = datetime(2026, 8, 18, 12, 14, 41, tzinfo=UTC)


class TestBackupIgnorePattern:
    def test_it_matches_a_name_the_backup_module_actually_writes(self, tmp_path: Path) -> None:
        """Derived from the real namer, so renaming the infix or restamping cannot orphan the rule."""
        backup = backup_path_for(path=tmp_path / "pipelex_override.toml", moment=MOMENT)

        assert fnmatch(backup.name, BACKUP_IGNORE_PATTERN)

    def test_it_matches_every_file_a_real_walk_can_back_up(self, tmp_path: Path) -> None:
        """The walk claims files by (directory, name), so the pattern must not lean on a stem."""
        for name in ("pipelex.toml", "pipelex_override.toml", "telemetry.toml", "anthropic.toml"):
            backup = backup_path_for(path=tmp_path / name, moment=MOMENT)
            assert fnmatch(backup.name, BACKUP_IGNORE_PATTERN), name

    def test_it_leaves_a_copy_the_user_named_themselves_alone(self) -> None:
        """`existing_backups_of` refuses to prune one of these; the ignore rule must not hide it."""
        assert not fnmatch("pipelex.toml.bak.notes", BACKUP_IGNORE_PATTERN)

    def test_a_rescue_copy_stays_visible(self, tmp_path: Path) -> None:
        """It is the one file the report tells the user to go and get — hiding it defeats the point."""
        rescue = rescue_path_for(path=tmp_path / "pipelex.toml", moment=MOMENT)

        assert not fnmatch(rescue.name, BACKUP_IGNORE_PATTERN)

    def test_it_does_not_hide_a_real_configuration_file(self) -> None:
        for name in ("pipelex.toml", "backends.toml", ".env"):
            assert not fnmatch(name, BACKUP_IGNORE_PATTERN), name


class TestEnsureConfigDirGitignore:
    def test_it_writes_the_file_when_the_directory_has_none(self, tmp_path: Path) -> None:
        was_written = ensure_config_dir_gitignore(directory=tmp_path)

        assert was_written is True
        assert (tmp_path / CONFIG_DIR_GITIGNORE_NAME).read_text().splitlines()[-1] == BACKUP_IGNORE_PATTERN

    def test_the_file_it_writes_actually_ignores_a_backup(self, tmp_path: Path) -> None:
        """The end the whole change exists for, asserted against git itself rather than by eye."""
        ensure_config_dir_gitignore(directory=tmp_path)
        written = (tmp_path / CONFIG_DIR_GITIGNORE_NAME).read_text()

        assert any(fnmatch("pipelex_override.toml.bak.20260818T121441Z", line) for line in written.splitlines() if line and not line.startswith("#"))

    def test_it_never_touches_a_gitignore_that_is_already_there(self, tmp_path: Path) -> None:
        """Once the file exists it is a file in the user's repo, and theirs to maintain."""
        theirs = tmp_path / CONFIG_DIR_GITIGNORE_NAME
        theirs.write_text("# mine\nstorage/\n")

        was_written = ensure_config_dir_gitignore(directory=tmp_path)

        assert was_written is False
        assert theirs.read_text() == "# mine\nstorage/\n"

    def test_running_it_twice_is_running_it_once(self, tmp_path: Path) -> None:
        ensure_config_dir_gitignore(directory=tmp_path)
        first = (tmp_path / CONFIG_DIR_GITIGNORE_NAME).read_text()

        was_written = ensure_config_dir_gitignore(directory=tmp_path)

        assert was_written is False
        assert (tmp_path / CONFIG_DIR_GITIGNORE_NAME).read_text() == first

    def test_a_directory_that_does_not_exist_is_left_alone(self, tmp_path: Path) -> None:
        """A walk skips a directory that is not there; ensuring one must not conjure it."""
        absent = tmp_path / "not_a_config_dir"

        was_written = ensure_config_dir_gitignore(directory=absent)

        assert was_written is False
        assert not absent.exists()


class TestARealRunEnsuresIt:
    """The wiring, asserted where it matters: a user who already has a `.pipelex/` gets the rule
    from the very run that would otherwise dirty their repository, not only from a fresh `init`.
    """

    def test_migrating_a_directory_leaves_the_rule_behind(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()

        migrate_config_directories(config_dirs=[config_dir], dry_run=False)

        assert (config_dir / CONFIG_DIR_GITIGNORE_NAME).is_file()

    def test_a_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        """`--dry-run` promises the disk is untouched, and a convenience file is still a write."""
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()

        migrate_config_directories(config_dirs=[config_dir], dry_run=True)

        assert not (config_dir / CONFIG_DIR_GITIGNORE_NAME).exists()

    def test_every_walked_directory_gets_one(self, tmp_path: Path) -> None:
        global_dir = tmp_path / "home" / ".pipelex"
        project_dir = tmp_path / "project" / ".pipelex"
        for directory in (global_dir, project_dir):
            directory.mkdir(parents=True)

        migrate_config_directories(config_dirs=[global_dir, project_dir], dry_run=False)

        assert (global_dir / CONFIG_DIR_GITIGNORE_NAME).is_file()
        assert (project_dir / CONFIG_DIR_GITIGNORE_NAME).is_file()

    def test_initializing_a_config_directory_writes_it(self, tmp_path: Path) -> None:
        target = tmp_path / ".pipelex"

        init_config(reset=False, target_dir=target)

        assert (target / CONFIG_DIR_GITIGNORE_NAME).is_file()

    def test_a_dry_run_init_writes_it_no_more_than_it_writes_anything_else(self, tmp_path: Path) -> None:
        target = tmp_path / ".pipelex"

        init_config(reset=False, dry_run=True, target_dir=target)

        assert not (target / CONFIG_DIR_GITIGNORE_NAME).exists()
