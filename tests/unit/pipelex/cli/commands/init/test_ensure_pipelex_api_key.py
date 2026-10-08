"""The hosted path keeps a key already set, else signs in through the browser, else names `pipelex login`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.credentials import set_env_file_entry
from pipelex.cli.commands.init.setup_path import ensure_pipelex_api_key
from pipelex.cli.commands.login.command import LoginOutcome
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from tests.helpers.recorded_console import RecordedConsole


class TestEnsurePipelexApiKey:
    def test_a_key_in_the_environment_skips_the_login(
        self, mocker: MockerFixture, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch, recorded_console: RecordedConsole
    ) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        check = mocker.patch("pipelex.cli.commands.login.command.check_pipelex_api_key")

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        login.assert_not_called()
        check.assert_not_called()
        assert "already set" in recorded_console.text()
        assert "plx_sk_test_not_a_secret" not in recorded_console.text()
        assert not (pipelex_home / ".env").exists()

    def test_a_working_directory_env_that_shadows_the_saved_key_is_named(
        self, mocker: MockerFixture, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch, recorded_console: RecordedConsole
    ) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")
        Path(".env").write_text(f"{PIPELEX_API_KEY_ENV_KEY}=plx_sk_project\n", encoding="utf-8")
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_project")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        login.assert_not_called()
        printed = recorded_console.text()
        assert "already set" in printed
        assert str(Path(".env").resolve()) in printed.replace("\n", "")
        assert "plx_sk_project" not in printed
        assert "plx_sk_saved" not in printed

    def test_a_saved_key_skips_the_login(self, mocker: MockerFixture, pipelex_home: Path, recorded_console: RecordedConsole) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        login.assert_not_called()

    @pytest.mark.usefixtures("pipelex_home")
    def test_a_key_that_does_not_look_like_one_is_kept_with_a_warning(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, recorded_console: RecordedConsole
    ) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "sk-something-else")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        login.assert_not_called()
        assert "does not look like a Pipelex API key" in recorded_console.text()

    @pytest.mark.usefixtures("pipelex_home")
    def test_with_no_key_it_signs_in_through_the_browser(self, mocker: MockerFixture, recorded_console: RecordedConsole) -> None:
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser", return_value=LoginOutcome.SAVED)

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        login.assert_called_once_with(console=recorded_console.console)
        assert "No key was saved" not in recorded_console.text()

    @pytest.mark.usefixtures("pipelex_home")
    def test_a_login_that_saved_nothing_names_pipelex_login(self, mocker: MockerFixture, recorded_console: RecordedConsole) -> None:
        mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser", return_value=LoginOutcome.NO_KEY)

        ensure_pipelex_api_key(console=recorded_console.console, interactive=True)

        assert "No key was saved" in recorded_console.text()
        assert "pipelex login" in recorded_console.text()

    @pytest.mark.usefixtures("pipelex_home")
    def test_with_nobody_to_answer_it_prints_pipelex_login_and_opens_no_browser(
        self, mocker: MockerFixture, recorded_console: RecordedConsole
    ) -> None:
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        browser_open = mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")

        ensure_pipelex_api_key(console=recorded_console.console, interactive=False)

        login.assert_not_called()
        browser_open.assert_not_called()
        assert "Run pipelex login" in recorded_console.text()
