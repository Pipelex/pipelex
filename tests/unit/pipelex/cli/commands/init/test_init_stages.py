"""`pipelex init`'s inspect stage decides, before anything is asked, whether the run asks where runs execute.

It also finds what a former release that ran on the Pipelex Gateway or Pipelex Manifold left, which the choose stage
offers to clean up before anything else is asked; the v0.72 kit, copied from that release's wheel, is the specimen.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.init.command import InitInspection, choose_initialization, describe_former_release_findings, inspect_initialization
from pipelex.cli.commands.init.setup_path import SetupPath, write_run_execution
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.former_release import detect_former_release

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


@pytest.fixture
def config_manager(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("pipelex.cli.commands.init.command.config_manager")


@pytest.fixture
def config_dir(tmp_path: Path, config_manager: MagicMock) -> Path:
    """The home configuration directory init targets, empty, and the only one the machine has: the boot reads its files."""
    directory = tmp_path / ".pipelex"
    config_manager.global_config_dir = directory
    config_manager.existing_config_dirs = [directory]
    config_manager.backends_file_paths.return_value = [directory / "inference" / "backends.toml", directory / "inference" / "backends_override.toml"]
    config_manager.routing_profiles_file_paths.return_value = [
        directory / "inference" / "routing_profiles.toml",
        directory / "inference" / "routing_profiles_override.toml",
    ]
    return directory


V0_72_CONFIG_DIR = "tests/data/migration/former_release/v0_72"


def _install_a_former_release(config_dir: Path) -> None:
    shutil.copytree(V0_72_CONFIG_DIR, config_dir)


def _snapshot(*, directory: Path) -> dict[str, bytes]:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


def _install_backends(config_dir: Path) -> None:
    inference_dir = config_dir / "inference"
    inference_dir.mkdir(parents=True)
    shutil.copy2(str(get_kit_configs_dir() / "inference" / "backends.toml"), inference_dir / "backends.toml")


def _inspect(*, focus: InitFocus) -> InitInspection:
    return inspect_initialization(focus=focus, local=False)


class TestInitStages:
    @pytest.mark.parametrize("focus", [InitFocus.ALL, InitFocus.CONFIG])
    def test_a_first_setup_asks_where_runs_execute(self, config_dir: Path, focus: InitFocus) -> None:
        inspection = _inspect(focus=focus)

        assert inspection.needs_inference
        assert inspection.asks_setup_path
        assert inspection.target_config_dir == config_dir
        assert not config_dir.exists(), "inspecting writes nothing"

    def test_a_full_reset_asks_again(self, config_dir: Path) -> None:
        _install_backends(config_dir)
        assert _inspect(focus=InitFocus.ALL).asks_setup_path

    def test_a_config_reset_of_an_existing_setup_keeps_the_setting(self, config_dir: Path) -> None:
        _install_backends(config_dir)
        write_run_execution(pipelex_toml_path=config_dir / "pipelex.toml", execution=RunExecution.HOSTED)

        inspection = _inspect(focus=InitFocus.CONFIG)

        assert not inspection.asks_setup_path
        assert inspection.configured_execution == RunExecution.HOSTED
        assert inspection.kept_execution == RunExecution.HOSTED
        assert inspection.keeps_hosted_runs

    @pytest.mark.parametrize("focus", [InitFocus.INFERENCE, InitFocus.ROUTING, InitFocus.TELEMETRY])
    def test_the_focused_setups_never_ask(self, config_dir: Path, focus: InitFocus) -> None:
        _install_backends(config_dir)
        inspection = _inspect(focus=focus)

        assert not inspection.asks_setup_path
        assert inspection.kept_execution is None

    @pytest.mark.usefixtures("config_dir")
    def test_without_anyone_to_answer_a_brand_new_home_takes_the_hosted_default(self, mocker: MockerFixture) -> None:
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path")
        confirm = mocker.patch("pipelex.cli.commands.init.command.Confirm.ask")

        choices = choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.CONFIG), skip_confirmation=True)

        assert choices.setup_path == SetupPath.HOSTED
        assert not choices.interactive
        prompt.assert_not_called()
        confirm.assert_not_called()

    @pytest.mark.parametrize("content", ["# written before [run] existed\n[log]\nlevel = 'info'\n", "", "[run\nbroken"])
    def test_without_anyone_to_answer_an_existing_pipelex_toml_without_the_setting_stays_local(
        self, config_dir: Path, mocker: MockerFixture, content: str
    ) -> None:
        """A `pipelex.toml` older than `[run]` runs on this machine, the package default, so a repair keeps it there."""
        config_dir.mkdir(parents=True)
        (config_dir / "pipelex.toml").write_text(content, encoding="utf-8")
        mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path")
        inspection = _inspect(focus=InitFocus.CONFIG)
        assert inspection.asks_setup_path
        assert inspection.configured_execution is None

        choices = choose_initialization(console=Console(quiet=True), inspection=inspection, skip_confirmation=True)

        assert choices.setup_path == SetupPath.LOCAL

    @pytest.mark.parametrize("configured", [RunExecution.LOCAL, RunExecution.HOSTED])
    def test_without_anyone_to_answer_a_configured_setting_is_kept(self, config_dir: Path, mocker: MockerFixture, configured: RunExecution) -> None:
        """`pipelex doctor --fix` installs what is missing; it never turns runs on this machine into hosted ones."""
        write_run_execution(pipelex_toml_path=config_dir / "pipelex.toml", execution=configured)
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path")
        inspection = _inspect(focus=InitFocus.CONFIG)
        assert inspection.asks_setup_path

        choices = choose_initialization(console=Console(quiet=True), inspection=inspection, skip_confirmation=True)

        assert choices.setup_path is not None
        assert choices.setup_path == SetupPath.from_run_execution(execution=configured)
        assert choices.setup_path.run_execution == configured
        prompt.assert_not_called()

    @pytest.mark.usefixtures("config_dir")
    def test_the_question_follows_the_confirmation(self, mocker: MockerFixture) -> None:
        calls: list[str] = []

        def confirm(*_args: object, **_kwargs: object) -> bool:
            calls.append("confirm")
            return True

        def ask_setup_path(**_kwargs: object) -> SetupPath:
            calls.append("setup_path")
            return SetupPath.LOCAL

        mocker.patch("pipelex.cli.commands.init.command.Confirm.ask", side_effect=confirm)
        mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path", side_effect=ask_setup_path)

        choices = choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.ALL), skip_confirmation=False)

        assert calls == ["confirm", "setup_path"]
        assert choices.setup_path == SetupPath.LOCAL
        assert choices.interactive

    def test_a_run_that_does_not_decide_it_asks_nothing_about_it(self, config_dir: Path, mocker: MockerFixture) -> None:
        _install_backends(config_dir)
        mocker.patch("pipelex.cli.commands.init.command.Confirm.ask", return_value=True)
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path")

        choices = choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.TELEMETRY), skip_confirmation=False)

        assert choices.setup_path is None
        prompt.assert_not_called()

    def test_the_inspection_finds_what_a_former_release_left_and_writes_nothing(self, config_dir: Path) -> None:
        _install_a_former_release(config_dir)
        before = _snapshot(directory=config_dir)

        inspection = _inspect(focus=InitFocus.ALL)

        assert [findings.config_dir for findings in inspection.former_release_findings] == [config_dir]
        assert inspection.former_release_boot_blockers
        assert _snapshot(directory=config_dir) == before

    def test_a_project_booting_on_a_base_of_its_own_is_not_told_it_cannot_start(
        self, config_dir: Path, config_manager: MagicMock, tmp_path: Path
    ) -> None:
        """The verdict is the boot's: the files it merges are the project's bases, which a former release never touched."""
        _install_a_former_release(config_dir)
        project_inference = tmp_path / "project" / ".pipelex" / "inference"
        shutil.copytree(Path(str(get_kit_configs_dir())) / "inference", project_inference)
        config_manager.backends_file_paths.return_value = [project_inference / "backends.toml", config_dir / "inference" / "backends_override.toml"]
        config_manager.routing_profiles_file_paths.return_value = [
            project_inference / "routing_profiles.toml",
            config_dir / "inference" / "routing_profiles_override.toml",
        ]

        inspection = _inspect(focus=InitFocus.ALL)

        assert inspection.former_release_findings, "the home still carries what the release left"
        assert inspection.former_release_boot_blockers == []
        description = describe_former_release_findings(findings=inspection.former_release_findings, blockers=inspection.former_release_boot_blockers)
        assert "no longer stops Pipelex from starting" in description

    def test_a_clean_target_has_no_former_release_findings(self, config_dir: Path) -> None:
        _install_backends(config_dir)
        assert _inspect(focus=InitFocus.ALL).former_release_findings == []

    def test_a_former_release_is_cleaned_up_on_yes_before_the_setup_question(self, config_dir: Path, mocker: MockerFixture) -> None:
        _install_a_former_release(config_dir)
        calls: list[str] = []

        def confirm(prompt: str, **_kwargs: object) -> bool:
            calls.append("clean_up" if "Clean it up" in prompt else "confirm")
            return True

        def ask_setup_path(**_kwargs: object) -> SetupPath:
            calls.append("setup_path")
            return SetupPath.LOCAL

        mocker.patch("pipelex.cli.commands.init.command.Confirm.ask", side_effect=confirm)
        mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path", side_effect=ask_setup_path)
        inspection = _inspect(focus=InitFocus.ALL)

        choose_initialization(console=Console(quiet=True), inspection=inspection, skip_confirmation=False)

        assert calls == ["clean_up", "confirm", "setup_path"]
        assert detect_former_release(config_dir=config_dir).is_clean

    def test_a_no_leaves_the_files_as_they_are_and_the_setup_goes_on(self, config_dir: Path, mocker: MockerFixture) -> None:
        _install_a_former_release(config_dir)
        before = _snapshot(directory=config_dir)

        def decline_the_cleanup_only(prompt: str, **_kwargs: object) -> bool:
            return "Clean it up" not in prompt

        mocker.patch("pipelex.cli.commands.init.command.Confirm.ask", side_effect=decline_the_cleanup_only)
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path", return_value=SetupPath.LOCAL)

        choices = choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.ALL), skip_confirmation=False)

        assert _snapshot(directory=config_dir) == before
        prompt.assert_called_once()
        assert choices.setup_path == SetupPath.LOCAL

    def test_without_anyone_to_answer_the_cleanup_never_runs(self, config_dir: Path, mocker: MockerFixture) -> None:
        """Nobody answers when `pipelex doctor --fix` calls init, and a cleanup nobody agreed to is not init's to run.

        The doctor asks its own question about the cleanup; whatever was answered there, init's unattended run leaves
        every file a former release left exactly as it found it.
        """
        _install_a_former_release(config_dir)
        before = _snapshot(directory=config_dir)
        confirm = mocker.patch("pipelex.cli.commands.init.command.Confirm.ask")

        choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.CONFIG), skip_confirmation=True)

        confirm.assert_not_called()
        assert _snapshot(directory=config_dir) == before
        assert not detect_former_release(config_dir=config_dir).is_clean

    @pytest.mark.parametrize("project_has_its_own_bases", [False, True])
    def test_a_no_says_pipelex_will_not_start_only_when_the_boot_would_refuse(
        self, config_dir: Path, config_manager: MagicMock, tmp_path: Path, mocker: MockerFixture, project_has_its_own_bases: bool
    ) -> None:
        _install_a_former_release(config_dir)
        if project_has_its_own_bases:
            project_inference = tmp_path / "project" / ".pipelex" / "inference"
            shutil.copytree(Path(str(get_kit_configs_dir())) / "inference", project_inference)
            config_manager.backends_file_paths.return_value = [project_inference / "backends.toml"]
            config_manager.routing_profiles_file_paths.return_value = [project_inference / "routing_profiles.toml"]

        def decline_the_cleanup_only(prompt: str, **_kwargs: object) -> bool:
            return "Clean it up" not in prompt

        mocker.patch("pipelex.cli.commands.init.command.Confirm.ask", side_effect=decline_the_cleanup_only)
        mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path", return_value=SetupPath.LOCAL)
        console = Console(record=True, width=400, color_system=None)

        choose_initialization(console=console, inspection=_inspect(focus=InitFocus.ALL), skip_confirmation=False)

        assert ("Pipelex will not start until then." in console.export_text()) is not project_has_its_own_bases
