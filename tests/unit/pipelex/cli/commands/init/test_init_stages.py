"""`pipelex init`'s inspect stage decides, before anything is asked, whether the run asks where runs execute."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.init.command import InitInspection, choose_initialization, inspect_initialization
from pipelex.cli.commands.init.setup_path import SetupPath, write_run_execution
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture
def config_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """The home configuration directory init targets, empty."""
    directory = tmp_path / ".pipelex"
    config_manager = mocker.MagicMock()
    config_manager.global_config_dir = directory
    mocker.patch("pipelex.cli.commands.init.command.config_manager", config_manager)
    return directory


def _install_backends(config_dir: Path) -> None:
    inference_dir = config_dir / "inference"
    inference_dir.mkdir(parents=True)
    shutil.copy2(str(get_kit_configs_dir() / "inference" / "backends.toml"), inference_dir / "backends.toml")


def _inspect(*, focus: InitFocus) -> InitInspection:
    return inspect_initialization(focus=focus, local=False)


class TestInspectInitialization:
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

    @pytest.mark.parametrize("focus", [InitFocus.INFERENCE, InitFocus.ROUTING, InitFocus.TELEMETRY])
    def test_the_focused_setups_never_ask(self, config_dir: Path, focus: InitFocus) -> None:
        _install_backends(config_dir)
        inspection = _inspect(focus=focus)

        assert not inspection.asks_setup_path
        assert inspection.kept_execution is None


class TestChooseInitialization:
    @pytest.mark.usefixtures("config_dir")
    def test_without_anyone_to_answer_the_hosted_default_is_taken(self, mocker: MockerFixture) -> None:
        prompt = mocker.patch("pipelex.cli.commands.init.command.prompt_setup_path")
        confirm = mocker.patch("pipelex.cli.commands.init.command.Confirm.ask")

        choices = choose_initialization(console=Console(quiet=True), inspection=_inspect(focus=InitFocus.CONFIG), skip_confirmation=True)

        assert choices.setup_path == SetupPath.HOSTED
        assert not choices.interactive
        prompt.assert_not_called()
        confirm.assert_not_called()

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
