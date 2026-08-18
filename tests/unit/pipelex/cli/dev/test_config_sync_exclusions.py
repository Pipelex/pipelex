"""What the `.pipelex` ↔ `pipelex/kit/configs` comparison must look past.

The kit holds the templates; a configuration directory in use also holds what pipelex itself writes
there — the `.gitignore` `ensure_config_dir_gitignore` creates, and the timestamped copies a
migration leaves behind. None of those has a kit counterpart, so a check comparing the two
directories by contents has to be told about each one, or it reports a project that has simply been
migrated as out of sync.

Every assertion below is made against a name the writing code actually produces, so a rename in
`pipelex/migration/` goes red here instead of quietly widening what the check reports.
"""

from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from pipelex.cli.dev_cli.config_sync_exclusions import CONFIG_SYNC_EXCLUDED_FILES, CONFIG_SYNC_EXCLUDED_PATTERNS
from pipelex.kit.paths import GIT_IGNORED_CONFIG_DIRS
from pipelex.migration.backup import backup_path_for, rescue_path_for
from pipelex.migration.gitignore import CONFIG_DIR_GITIGNORE_NAME, ensure_config_dir_gitignore
from pipelex.tools.misc.diff import has_diff_dirs

MOMENT = datetime(2026, 8, 18, 12, 14, 41, tzinfo=UTC)


class TestConfigSyncExclusions:
    def test_the_config_directory_gitignore_is_excluded(self) -> None:
        """It is written into the directory at init and at migrate, and is never a kit template."""
        assert CONFIG_DIR_GITIGNORE_NAME in CONFIG_SYNC_EXCLUDED_FILES

    def test_a_real_backup_name_is_excluded(self) -> None:
        """Migrating in a checkout must not make the next `make check` red."""
        backup = backup_path_for(path=Path("pipelex_override.toml"), moment=MOMENT)

        assert any(fnmatchcase(backup.name, pattern) for pattern in CONFIG_SYNC_EXCLUDED_PATTERNS)

    def test_a_real_rescue_name_is_excluded(self) -> None:
        """Still visible in `git status`, where the reminder belongs — just not read as a config."""
        rescue = rescue_path_for(path=Path("pipelex.toml"), moment=MOMENT)

        assert any(fnmatchcase(rescue.name, pattern) for pattern in CONFIG_SYNC_EXCLUDED_PATTERNS)

    def test_every_file_a_real_walk_can_back_up_is_excluded(self) -> None:
        """The walk claims files by (directory, name), so the patterns must not lean on a stem."""
        for name in ("pipelex.toml", "pipelex_override.toml", "telemetry.toml", "anthropic.toml"):
            backup = backup_path_for(path=Path(name), moment=MOMENT)
            assert any(fnmatchcase(backup.name, pattern) for pattern in CONFIG_SYNC_EXCLUDED_PATTERNS), name

    def test_a_copy_the_user_named_themselves_is_not_excluded(self) -> None:
        """Pruning refuses to manage one of these; the check has no business hiding it either."""
        for name in ("pipelex.toml.bak.notes", "pipelex.toml.bak.1-notesZ", "pipelex.toml.rescue.keep"):
            assert not any(fnmatchcase(name, pattern) for pattern in CONFIG_SYNC_EXCLUDED_PATTERNS), name

    def test_a_migrated_config_directory_reads_as_in_sync(self, tmp_path: Path) -> None:
        """The whole chain, against a directory carrying everything a real migration leaves.

        Asserted through `has_diff_dirs` with the real constants rather than against the constants
        alone, so a command that stopped passing them would fail here too.
        """
        kit_side = tmp_path / "kit"
        project_side = tmp_path / "project"
        kit_side.mkdir()
        project_side.mkdir()
        (kit_side / "pipelex.toml").write_text("shared = true", encoding="utf-8")
        (project_side / "pipelex.toml").write_text("shared = true", encoding="utf-8")

        ensure_config_dir_gitignore(directory=project_side)
        backup_path_for(path=project_side / "pipelex.toml", moment=MOMENT).write_text("shared = false", encoding="utf-8")
        rescue_path_for(path=project_side / "pipelex.toml", moment=MOMENT).write_text("shared = false", encoding="utf-8")

        assert (
            has_diff_dirs(
                dir1=project_side,
                dir2=kit_side,
                exclude_files=CONFIG_SYNC_EXCLUDED_FILES,
                exclude_dirs=GIT_IGNORED_CONFIG_DIRS,
                exclude_patterns=CONFIG_SYNC_EXCLUDED_PATTERNS,
            )
            is False
        )
