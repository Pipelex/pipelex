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
from pipelex.kit.paths import RETIRED_SERVICE_FILE_NAME, get_kit_configs_dir
from pipelex.migration.backup import existing_backups_of
from pipelex.migration.former_release import detect_former_release, kit_default_routing_profile_name
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

V0_72_CONFIG_DIR = Path("tests/data/migration/former_release/v0_72")
V0_72_CLEANED_DIR = Path("tests/data/migration/former_release/v0_72_cleaned")

# The files the cleanup touches in the v0.72 directory, rewritten or removed.
V0_72_FILE_COUNT = len(detect_former_release(config_dir=V0_72_CONFIG_DIR).file_paths)

# A model table whose key the inference-backend ledger renames, and a key no schema knows.
MIGRATABLE_MODEL_TABLE = '\n["gpt-4o"]\nprompting_target = "openai"\n'
UNKNOWN_MODEL_TABLE = '\n["claude-x"]\nsome_unknown_key = 1\n'


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
        assert not (former_release_machine / RETIRED_SERVICE_FILE_NAME).exists(), "a removal does not go through the commit that failed"

    def test_a_file_the_cleanup_removes_is_not_counted_among_the_files_to_migrate(
        self, former_release_machine: Path, console: Console, mocker: MockerFixture
    ) -> None:
        """A key the ledger would carry forward, in a retired backend's file: the file goes, so nothing of it is migrated."""
        gateway_file = former_release_machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "pipelex_gateway.toml"
        with gateway_file.open("a", encoding="utf-8") as stream:
            stream.write(MIGRATABLE_MODEL_TABLE)
        asked = mocker.patch.object(migrate_cmd_module.Confirm, "ask", return_value=False)

        migrate_cmd()

        assert asked.call_args.args[0] == f"[bold]Clean up {V0_72_FILE_COUNT} file(s)?[/bold]"
        assert f"{gateway_file} (inference-backend)" not in console.export_text()

    def test_an_unknown_key_in_a_file_the_cleanup_removes_needs_no_attention(self, former_release_machine: Path, console: Console) -> None:
        manifold_file = former_release_machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "pipelex_manifold.toml"
        with manifold_file.open("a", encoding="utf-8") as stream:
            stream.write(UNKNOWN_MODEL_TABLE)

        migrate_cmd(dry_run=True)

        assert "some_unknown_key" not in console.export_text()

    def test_a_machine_that_still_cannot_start_after_the_cleanup_is_reported_and_exits_non_zero(
        self, former_release_machine: Path, console: Console
    ) -> None:
        """The check after the write: an `active` naming a profile no file defines still stops the boot, and success is not claimed."""
        routing_path = former_release_machine / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME
        text = routing_path.read_text(encoding="utf-8")
        assert text.count('active = "all_pipelex_gateway"') == 1
        routing_path.write_text(text.replace('active = "all_pipelex_gateway"', 'active = "ghost"'), encoding="utf-8")

        with pytest.raises(SystemExit) as leaving:
            migrate_cmd(yes=True)

        assert leaving.value.code == 1
        output = console.export_text()
        assert "After the cleanup, Pipelex still cannot start:" in output
        assert "'ghost'" in output
        assert "a copy of each original is beside it" not in output

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_a_machine_with_nothing_left_to_clean_that_cannot_start_is_never_up_to_date(
        self, tmp_path: Path, console: Console, mocker: MockerFixture, dry_run: bool
    ) -> None:
        """A cleanup left half done — run from another project, or stopped by a file it could not write — leaves no file a
        former release left and a boot still stopped: the retry says what stops it, and exits non-zero.
        """
        config_dir = tmp_path / ".pipelex"
        shutil.copytree(Path(str(get_kit_configs_dir())), config_dir)
        routing_path = config_dir / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME
        text = routing_path.read_text(encoding="utf-8")
        routing_path.write_text(text.replace(f'active = "{kit_default_routing_profile_name()}"', 'active = "team_gateway"'), encoding="utf-8")
        mocker.patch.object(migrate_cmd_module, "config_directories_to_migrate", return_value=[config_dir])

        with pytest.raises(SystemExit) as leaving:
            migrate_cmd(dry_run=dry_run, yes=not dry_run)

        assert leaving.value.code == 1
        output = console.export_text()
        assert "Pipelex cannot start:" in output
        assert "'team_gateway'" in output
        assert "at the current schema" not in output
        assert "file(s)?" not in output
