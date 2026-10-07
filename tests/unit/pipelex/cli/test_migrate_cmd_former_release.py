"""`pipelex migrate` on a machine a former release set up: the cleanup is its first step, rehearsed, asked about and reported.

The machine is the v0.72 kit, copied from that release's wheel, as one configuration directory. Its ledger-claimed
files are already at the current schema, so everything the command has to do here is the cleanup, which is what lets
each test say exactly what the command printed and wrote.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands import migrate_cmd as migrate_cmd_module
from pipelex.cli.commands.migrate_cmd import migrate_cmd
from pipelex.migration.backup import existing_backups_of
from pipelex.migration.former_release import SERVICE_FILE_NAME, detect_former_release
from pipelex.system.configuration.config_loader import BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")
V0_72_CLEANED_DIR = Path("tests/data/migration/former_release/v0_72_cleaned")

# The files the cleanup touches in the v0.72 directory: two rewritten, five removed.
V0_72_FILE_COUNT = 7


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    recorded = Console(width=400, record=True, color_system=None)
    mocker.patch.object(migrate_cmd_module, "get_console", return_value=recorded)
    return recorded


@pytest.fixture
def former_release_machine(tmp_path: Path, mocker: MockerFixture) -> Path:
    config_dir = tmp_path / ".pipelex"
    shutil.copytree(V0_72_CONFIG_DIR, config_dir)
    mocker.patch.object(migrate_cmd_module, "config_directories_to_migrate", return_value=[config_dir])
    return config_dir


def _snapshot(*, directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


class TestTheMigrateCommandOnAFormerRelease:
    def test_yes_cleans_up_every_file_and_says_so(self, former_release_machine: Path, console: Console) -> None:
        migrate_cmd(yes=True)

        output = console.export_text()
        inference_dir = former_release_machine / INFERENCE_DIR_NAME
        assert str(inference_dir / BACKENDS_FILE_NAME) in output
        assert "✓ removed the 'pipelex_gateway' backend" in output
        assert "✓ moved the active routing profile from 'all_pipelex_gateway' to 'all_enabled_backends'" in output
        assert f"backup: {inference_dir / BACKENDS_FILE_NAME}.bak." in output
        assert f"Cleaned up {V0_72_FILE_COUNT} file(s) a former release left; a copy of each original is beside it." in output
        for name in (BACKENDS_FILE_NAME, ROUTING_PROFILES_FILE_NAME):
            assert (inference_dir / name).read_bytes() == (V0_72_CLEANED_DIR / INFERENCE_DIR_NAME / name).read_bytes()
        assert detect_former_release(config_dir=former_release_machine).is_clean

    def test_a_dry_run_rehearses_the_cleanup_and_writes_nothing(self, former_release_machine: Path, console: Console) -> None:
        before = _snapshot(directory=former_release_machine)

        migrate_cmd(dry_run=True)

        output = console.export_text()
        assert "→ removed the 'pipelex_gateway' backend" in output
        assert "→ removed the record of the Pipelex Gateway's terms acceptance" in output
        assert "Dry run — nothing was written." in output
        assert _snapshot(directory=former_release_machine) == before

    def test_the_question_counts_the_cleanup_and_a_no_writes_nothing(
        self, former_release_machine: Path, console: Console, mocker: MockerFixture
    ) -> None:
        before = _snapshot(directory=former_release_machine)
        asked = mocker.patch.object(migrate_cmd_module.Confirm, "ask", return_value=False)

        migrate_cmd()

        assert f"Clean up {V0_72_FILE_COUNT} file(s)?" in asked.call_args.args[0]
        assert "nothing was written" in console.export_text()
        assert _snapshot(directory=former_release_machine) == before

    def test_a_file_the_cleanup_could_not_write_leaves_a_non_zero_exit(
        self, former_release_machine: Path, console: Console, mocker: MockerFixture
    ) -> None:
        mocker.patch("pipelex.migration.runner.commit_file_updates", side_effect=PermissionError(13, "Permission denied"))

        with pytest.raises(SystemExit) as leaving:
            migrate_cmd(yes=True)

        assert leaving.value.code == 1
        output = console.export_text()
        assert "✗ unwritable" in output
        routing_path = former_release_machine / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME
        assert routing_path.read_bytes() == (V0_72_CONFIG_DIR / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME).read_bytes()
        assert existing_backups_of(path=routing_path) == []
        assert not (former_release_machine / SERVICE_FILE_NAME).exists(), "a removal does not go through the commit that failed"
