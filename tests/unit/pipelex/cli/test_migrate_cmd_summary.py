"""What the summary panel of `pipelex migrate` says once the write pass has run.

The per-file lines above the panel are the runner's account; the panel is the command's one-line
verdict on the run, and it must not contradict the lines it closes. One state makes that easy to
get wrong: a transaction that left a file's state uncertain has *not* left it as it was found, so
"Nothing was written." would be a false comfort right under a line telling the user to compare the
file against its rescue copy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands import migrate_cmd as migrate_cmd_module
from pipelex.cli.commands.migrate_cmd import migrate_cmd
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError
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
def stale_machine(tmp_path: Path, mocker: MockerFixture) -> Path:
    """One configuration directory holding the flat telemetry document the shipped entry carries forward."""
    config_dir = tmp_path / ".pipelex"
    config_dir.mkdir()
    old_shape = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    stale = config_dir / "telemetry.toml"
    stale.write_text(old_shape.read_text(encoding="utf-8"), encoding="utf-8")
    mocker.patch.object(migrate_cmd_module, "config_directories_to_migrate", return_value=[config_dir])
    return stale


@pytest.mark.usefixtures("stale_machine")
class TestTheSummaryPanel:
    def test_an_uncertain_write_is_not_reported_as_nothing_written(self, console: Console, mocker: MockerFixture) -> None:
        """The transaction replaced the file and could not say what it left; the copy is the user's next move."""
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=FixTransactionError("commit failed and rollback was incomplete"))

        with pytest.raises(SystemExit) as leaving:
            migrate_cmd(yes=True)

        assert leaving.value.code == 1, "a file a person has to look at"
        output = console.export_text()
        assert "Nothing was written" not in output
        assert "No write could be confirmed" in output
        assert "state_uncertain" in output

    def test_a_write_the_run_refused_still_says_nothing_was_written(self, console: Console, mocker: MockerFixture) -> None:
        """The other blocked reasons keep the file exactly as it was found, and the panel says so."""
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=FixWriteConflictError("the file changed under the run"))

        with pytest.raises(SystemExit):
            migrate_cmd(yes=True)

        output = console.export_text()
        assert "Nothing was written." in output
        assert "No write could be confirmed" not in output
