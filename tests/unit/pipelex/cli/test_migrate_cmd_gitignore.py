"""Whether `pipelex migrate` leaves the config-directory `.gitignore` behind, as a user runs it.

`tests/unit/pipelex/migration/test_config_dir_gitignore.py` proves the engine writes the rule when
it writes anything. That is one layer below where the user stands, and the command has an early
return the engine never sees: a machine whose files are all at the current schema is reported clean
and the write pass is never called at all.

That machine is the steady state, not an edge case — it is every user who migrated once and then
upgraded, which is exactly the population the rule was promised to. Asserting the wiring on the
engine alone is how the gap stayed invisible, so it is asserted here on the command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands import migrate_cmd as migrate_cmd_module
from pipelex.cli.commands.migrate_cmd import migrate_cmd
from pipelex.migration.gitignore import CONFIG_DIR_GITIGNORE_NAME
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.system.configuration.config_surface import TELEMETRY_CONFIG_SURFACE_ID

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    recorded = Console(width=200, record=True, color_system=None)
    mocker.patch.object(migrate_cmd_module, "get_console", return_value=recorded)
    return recorded


@pytest.fixture
def clean_machine(tmp_path: Path, mocker: MockerFixture) -> Path:
    """One configuration directory with nothing in it for the ledger to carry forward."""
    config_dir = tmp_path / ".pipelex"
    config_dir.mkdir()
    mocker.patch.object(migrate_cmd_module, "config_directories_to_migrate", return_value=[config_dir])
    return config_dir


class TestTheCommandEnsuresTheGitignore:
    def test_a_machine_with_nothing_to_migrate_still_gets_the_rule(self, clean_machine: Path, console: Console) -> None:
        migrate_cmd(yes=True)

        # Pins that this went down the clean early return rather than the write pass, so the test
        # cannot quietly start proving what the engine tests already prove.
        assert "current schema" in console.export_text()
        assert (clean_machine / CONFIG_DIR_GITIGNORE_NAME).is_file()

    def test_a_dry_run_over_a_clean_machine_writes_nothing(self, clean_machine: Path, console: Console) -> None:
        """`--dry-run` promises the disk is untouched, and that promise outranks the convenience."""
        migrate_cmd(dry_run=True)

        assert "current schema" in console.export_text()
        assert not (clean_machine / CONFIG_DIR_GITIGNORE_NAME).exists()

    def test_a_declined_migration_still_writes_nothing(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        """The deliberate other half: a person's "no" to the write is a no to every write in the run.

        The rule lands on the clean path because no question was pending there. Here one was, and it
        was answered no — "Migration cancelled — nothing was written" has to stay true of the whole
        directory, the convenience file included.
        """
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()
        old_shape = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
        (config_dir / "telemetry.toml").write_text(old_shape.read_text(encoding="utf-8"), encoding="utf-8")
        mocker.patch.object(migrate_cmd_module, "config_directories_to_migrate", return_value=[config_dir])
        mocker.patch.object(migrate_cmd_module.Confirm, "ask", return_value=False)

        migrate_cmd()

        assert "cancelled" in console.export_text().lower()
        assert not (config_dir / CONFIG_DIR_GITIGNORE_NAME).exists()
