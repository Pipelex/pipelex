"""The doctor's configuration-migration row: what a dry run of `pipelex migrate` found.

Nothing else tells a machine this. A stale configuration the ledger can explain boots with a
warning, and the agent CLI cuts logging off process-wide before one can be emitted — so for a
machine consumer, asking is the only channel, and this row is the asking.

The row differs from every other check in the doctor in one way that is a decision rather than an
oversight: **it takes no directory**. The others report on a *file* and are scoped to the directory
the doctor was pointed at, `--global` included. This one reports on a *command*, and `pipelex
migrate` has no `--global` — it walks the global `~/.pipelex/` and the project `.pipelex/` both. A
row scoped narrower would name a command that then rewrites a file the row never mentioned.

The stale document here is the package's own: `telemetry-config@2` is the shipped entry and
`goldens/telemetry-config/before@2.toml` is the flat document it exists to carry forward.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

from pipelex.cli.commands.doctor_cmd import PendingMigrationsFinding, check_pending_migrations
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.migration.backup import existing_backups_of
from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.system.configuration.config_surface import TELEMETRY_CONFIG_SURFACE_ID

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# A realistic PostHog project key, at the path the shipped entry moves. The old flat format is
# exactly where a real one would be, which makes this the right specimen for the rendering rule.
PLANTED_KEY = "phc_L1VE_telemetry_key_that_must_never_be_rendered"

UNKNOWN_ROOT_KEY = "not_a_real_setting"


def old_shape_document() -> str:
    """The flat pre-`[custom_posthog]` document the shipped entry is about, read from the package."""
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


class Machine(NamedTuple):
    """The two configuration directories a migration walks, on a fake home."""

    global_dir: Path
    project_dir: Path


@pytest.fixture
def machine(tmp_path: Path, mocker: MockerFixture) -> Machine:
    """A fake home and a fake project, so the walk reads this test's files and not the machine's."""
    fake_home = tmp_path / "home"
    global_dir = fake_home / ".pipelex"
    global_dir.mkdir(parents=True)

    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    project_dir = project_root / ".pipelex"
    project_dir.mkdir()

    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)

    return Machine(global_dir=global_dir, project_dir=project_dir)


class TestWhatTheRowReports:
    """The verdict, the files it names, and the two things the row must never do."""

    @pytest.mark.usefixtures("machine")
    def test_a_machine_at_the_current_schema_has_nothing_pending(self) -> None:
        """Two empty configuration directories are two directories with nothing to do."""
        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.UP_TO_DATE
        assert check.is_healthy is True
        assert check.migratable_files == []
        assert check.attention_files == []

    def test_a_stale_file_is_pending_and_the_row_names_it(self, machine: Machine) -> None:
        """The remedy is the command, and the file it would rewrite is named with its full path."""
        stale = machine.global_dir / "telemetry.toml"
        stale.write_text(old_shape_document(), encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.PENDING
        assert check.finding.is_repaired_by_migrating is True
        assert check.migratable_files == [str(stale)]
        assert MIGRATE_COMMAND in check.message

    def test_a_file_no_ledger_explains_needs_a_look_rather_than_a_command(self, machine: Machine) -> None:
        """A root key this build knows nothing about is a person's, and `--fix` must not offer it.

        The migration would write nothing here, so a row that reported it as pending would send a
        user to a command that runs and changes nothing — and, in fix mode, would offer to do it.
        """
        broken = machine.project_dir / "pipelex.toml"
        broken.write_text(f"{UNKNOWN_ROOT_KEY} = true\n", encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.NEEDS_ATTENTION
        assert check.finding.is_repaired_by_migrating is False
        assert check.migratable_files == []
        assert check.attention_files == [str(broken)]

    def test_a_run_that_both_migrates_and_leaves_something_reports_both(self, machine: Machine) -> None:
        """The ordinary shape on a machine that has drifted, and the one a single verdict flattens."""
        stale = machine.global_dir / "telemetry.toml"
        stale.write_text(old_shape_document(), encoding="utf-8")
        broken = machine.project_dir / "pipelex.toml"
        broken.write_text(f"{UNKNOWN_ROOT_KEY} = true\n", encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.PENDING, "there is still something to run"
        assert check.migratable_files == [str(stale)]
        assert check.attention_files == [str(broken)]

    def test_a_stale_file_in_either_directory_is_reported(self, machine: Machine) -> None:
        """Both directories, because both are what `pipelex migrate` would rewrite.

        A row scoped to the directory the doctor resolved would leave the other one out, and the
        command it names would then touch a file the reader was never shown.
        """
        global_stale = machine.global_dir / "telemetry.toml"
        global_stale.write_text(old_shape_document(), encoding="utf-8")
        project_stale = machine.project_dir / "telemetry_override.toml"
        project_stale.write_text('telemetry_mode = "off"\n', encoding="utf-8")

        check = check_pending_migrations()

        assert sorted(check.migratable_files) == sorted([str(global_stale), str(project_stale)])

    def test_the_row_is_a_dry_run_and_leaves_the_files_exactly_as_it_found_them(self, machine: Machine) -> None:
        """A health report that repaired what it reported would be a command, not a report."""
        stale = machine.global_dir / "telemetry.toml"
        before = old_shape_document()
        stale.write_text(before, encoding="utf-8")

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.PENDING
        assert stale.read_text(encoding="utf-8") == before
        assert existing_backups_of(path=stale) == [], "a dry run writes nothing, backups included"

    @pytest.mark.usefixtures("machine")
    def test_a_broken_ledger_is_reported_as_a_failure_to_check(self, mocker: MockerFixture) -> None:
        """An exception here would reach the doctor's outer handler and take every row with it.

        That handler prints one line and exits, so a packaging problem of ours would replace the
        whole health report. Saying we could not look is honest and costs the user one row.
        """
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.migrate_config_directories",
            side_effect=MigrationLedgerError("the packaged ledger will not load"),
        )

        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.UNAVAILABLE
        assert check.finding.is_uncheckable is True
        assert check.is_healthy is False, "not knowing is not the same as being up to date"
        assert "the packaged ledger will not load" in check.message

    @pytest.mark.usefixtures("machine")
    def test_an_unexpected_bug_still_surfaces_as_itself(self, mocker: MockerFixture) -> None:
        """The catch is narrow on purpose: a bug in our applier is not a field condition."""
        mocker.patch(
            "pipelex.cli.commands.doctor_cmd.migrate_config_directories",
            side_effect=RuntimeError("an applier bug"),
        )

        with pytest.raises(RuntimeError, match="an applier bug"):
            check_pending_migrations()


class TestNoValueFromAUsersFileIsEverRendered:
    """The mechanical rule, on the row that reads every configuration file on the machine."""

    def test_a_planted_secret_reaches_neither_the_message_nor_the_file_lists(self, machine: Machine) -> None:
        stale = machine.global_dir / "telemetry.toml"
        document = old_shape_document().replace('project_api_key = "phc_example_project_api_key"', f'project_api_key = "{PLANTED_KEY}"')
        assert PLANTED_KEY in document, "the specimen must actually carry the secret"
        stale.write_text(document, encoding="utf-8")

        check = check_pending_migrations()

        assert PLANTED_KEY in stale.read_text(encoding="utf-8")
        assert PLANTED_KEY not in str(check.model_dump(mode="json"))
