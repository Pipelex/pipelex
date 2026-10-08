"""The hosted path's last step, getting a Pipelex API key, fails without undoing or misreporting the setup written before it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.commands.init.command import InitChoices, execute_initialization, inspect_initialization
from pipelex.cli.commands.init.setup_path import SetupPath, read_run_execution
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND
from pipelex.hosted.run_config import RunExecution

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests.helpers.recorded_console import RecordedConsole


class TestHostedKeyStep:
    def test_a_listener_that_cannot_bind_leaves_the_setup_saved_and_names_pipelex_login(
        self, mocker: MockerFixture, pipelex_home: Path, recorded_console: RecordedConsole
    ) -> None:
        mocker.patch("pipelex.cli.commands.init.command.suggest_extension_install_if_needed")
        mocker.patch("pipelex.cli.commands.login.command.LoopbackListener", side_effect=OSError(48, "Address already in use"))
        browser_open = mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")
        inspection = inspect_initialization(focus=InitFocus.ALL, local=False)

        execute_initialization(
            console=recorded_console.console, inspection=inspection, choices=InitChoices(setup_path=SetupPath.HOSTED, interactive=True)
        )

        browser_open.assert_not_called()
        assert read_run_execution(pipelex_toml_path=pipelex_home / "pipelex.toml") == RunExecution.HOSTED
        assert (pipelex_home / "telemetry.toml").is_file()
        # Rich wraps long lines at spaces; joining the words back reads the message as written
        printed = " ".join(recorded_console.text().split())
        assert "Address already in use" in printed
        assert "pipelex login" in printed
        assert LOGIN_PASTE_COMMAND in printed
        assert "pipelex init config" not in printed
