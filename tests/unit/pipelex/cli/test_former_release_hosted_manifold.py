"""The hosted plane's configuration is not a former release's: Pipelex Manifold is live, and nothing refuses or cleans it.

The Pipelex Gateway is retired; Pipelex Manifold is not. The hosted plane runs every model through it, with a plugin of
its own, and each of its members that boots Pipelex — the runner, the worker and the Temporal suite — ships a
`.pipelex/inference/` declaring an enabled `[pipelex_manifold]` backend, an `all_pipelex_manifold` profile made active,
and the model registry's runtime slice as `backends/pipelex_manifold.toml`. `tests/data/migration/former_release/hosted_manifold/`
holds those trees as the hosted plane ships them, the slice cut to two models. Each stands as a project's `.pipelex/`
beside a home holding the current kit, which is what a boot fills a home configuration directory with: no boot of it is
refused, and no command that finds or cleans what a former release left finds anything here or writes anything.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.migrate_cmd import agent_migrate_cmd
from pipelex.cli.commands import migrate_cmd as migrate_cmd_module
from pipelex.cli.commands.doctor_cmd import PendingMigrationsFinding, check_backend_credentials, check_pending_migrations
from pipelex.cli.commands.init.command import inspect_initialization
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.migrate_cmd import migrate_cmd
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.former_release import detect_former_release_across, former_release_boot_blockers
from pipelex.migration.former_release_cleanup import clean_former_release, what_stops_the_boot
from pipelex.system.configuration.config_loader import BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

pytestmark = pytest.mark.usefixtures("no_pipelex_home")

HOSTED_MANIFOLD_DIR = Path("tests/data/migration/former_release/hosted_manifold")

#: The members of the hosted plane that boot Pipelex, each with the `.pipelex/inference/` it ships.
HOSTED_MEMBERS = ["api-hosted", "worker", "temporal"]


@pytest.fixture(params=HOSTED_MEMBERS)
def hosted_machine(request: pytest.FixtureRequest, tmp_path: Path, mocker: MockerFixture) -> tuple[Path, Path]:
    """A home holding the current kit, and a project whose `.pipelex/` is one hosted member's: the home's and the project's."""
    fake_home = tmp_path / "home"
    home_config_dir = fake_home / ".pipelex"
    shutil.copytree(Path(str(get_kit_configs_dir())), home_config_dir)
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    project_config_dir = project_root / ".pipelex"
    shutil.copytree(HOSTED_MANIFOLD_DIR / request.param, project_config_dir)
    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)
    return home_config_dir, project_config_dir


def _snapshot(*, directories: tuple[Path, ...]) -> dict[str, bytes]:
    return {str(path): path.read_bytes() for directory in directories for path in sorted(directory.rglob("*")) if path.is_file()}


class TestTheHostedPlanesManifoldConfiguration:
    def test_no_boot_of_it_is_refused(self, hosted_machine: tuple[Path, Path]) -> None:
        _, project_config_dir = hosted_machine
        inference_dir = project_config_dir / INFERENCE_DIR_NAME

        blockers = former_release_boot_blockers(
            backends_library_paths=[inference_dir / BACKENDS_FILE_NAME],
            routing_profile_library_paths=[inference_dir / ROUTING_PROFILES_FILE_NAME],
        )

        assert blockers == []
        assert what_stops_the_boot(config_dirs=list(hosted_machine)) == []

    def test_nothing_in_it_is_what_a_former_release_left(self, hosted_machine: tuple[Path, Path]) -> None:
        assert all(findings.is_clean for findings in detect_former_release_across(config_dirs=list(hosted_machine)))

    def test_the_cleanup_finds_nothing_and_writes_nothing(self, hosted_machine: tuple[Path, Path]) -> None:
        before = _snapshot(directories=hosted_machine)

        cleanup = clean_former_release(config_dirs=list(hosted_machine), dry_run=False)

        assert cleanup.is_clean
        assert cleanup.files == []
        assert _snapshot(directories=hosted_machine) == before

    def test_pipelex_migrate_dry_run_has_nothing_to_do(self, hosted_machine: tuple[Path, Path], mocker: MockerFixture) -> None:
        console = Console(width=400, record=True, color_system=None)
        mocker.patch.object(migrate_cmd_module, "get_console", return_value=console)
        before = _snapshot(directories=hosted_machine)

        migrate_cmd(dry_run=True)

        output = console.export_text()
        assert "Every configuration file on this machine is at the current schema." in output
        assert "former release" not in output
        assert _snapshot(directories=hosted_machine) == before

    @pytest.mark.usefixtures("hosted_machine")
    def test_pipelex_agent_migrate_reports_a_clean_machine(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.migrate_cmd.silence_logging_for_agent_cli")

        agent_migrate_cmd(output_format=CliOutputFormat.JSON)

        result = json.loads(capsys.readouterr().out)
        assert result["is_clean"] is True
        assert result["needs_attention"] is False
        assert result["former_release"] == {"is_clean": True, "needs_attention": False, "files": [], "still_blocking": []}

    @pytest.mark.usefixtures("hosted_machine")
    def test_the_doctors_migrations_row_is_up_to_date(self) -> None:
        check = check_pending_migrations()

        assert check.finding is PendingMigrationsFinding.UP_TO_DATE
        assert check.former_release_files == []

    def test_the_doctor_checks_manifolds_credentials(self, hosted_machine: tuple[Path, Path]) -> None:
        """An enabled `pipelex_manifold` backend is one like any other: its endpoint and key are checked, never skipped as retired."""
        _, project_config_dir = hosted_machine

        _, backend_reports, _ = check_backend_credentials(config_dir=project_config_dir)

        assert "pipelex_manifold" in backend_reports

    @pytest.mark.usefixtures("hosted_machine")
    def test_init_finds_nothing_to_offer_to_clean_up(self) -> None:
        inspection = inspect_initialization(focus=InitFocus.ALL, local=True)

        assert inspection.former_release_findings == []
        assert inspection.former_release_boot_blockers == []
