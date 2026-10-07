"""Where runs execute: the question, its default, the setting it writes, and the key the hosted path needs."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.init.credentials import set_env_file_entry
from pipelex.cli.commands.init.setup_path import (
    DEFAULT_SETUP_PATH,
    SetupPath,
    ensure_pipelex_api_key,
    read_run_execution,
    write_run_execution,
)
from pipelex.cli.commands.init.ui.setup_path_ui import SETUP_PATH_QUESTION, prompt_setup_path
from pipelex.cli.commands.login.command import LoginOutcome
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=200), buffer


class TestPromptSetupPath:
    def test_hosted_is_the_default(self) -> None:
        assert DEFAULT_SETUP_PATH == SetupPath.HOSTED

    def test_enter_takes_the_hosted_api_listed_first(self, mocker: MockerFixture) -> None:
        console, buffer = _console()

        def press_enter(*_args: object, default: str, **_kwargs: object) -> str:
            return default

        prompt = mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", side_effect=press_enter)

        assert prompt_setup_path(console=console) == SetupPath.HOSTED

        assert prompt.call_args.kwargs["default"] == "1"
        shown = buffer.getvalue()
        assert SETUP_PATH_QUESTION in shown
        assert shown.index("On the hosted Pipelex API, with a Pipelex API key") < shown.index("On this machine, with your own provider keys")

    @pytest.mark.parametrize(
        ("answer", "expected"),
        [("", SetupPath.HOSTED), ("1", SetupPath.HOSTED), ("2", SetupPath.LOCAL), ("local", SetupPath.LOCAL), (" Hosted ", SetupPath.HOSTED)],
    )
    def test_a_number_or_a_name_picks_the_path(self, mocker: MockerFixture, answer: str, expected: SetupPath) -> None:
        console, _ = _console()
        mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", return_value=answer)

        assert prompt_setup_path(console=console) == expected

    def test_anything_else_asks_again(self, mocker: MockerFixture) -> None:
        console, buffer = _console()
        prompt = mocker.patch("pipelex.cli.commands.init.ui.setup_path_ui.Prompt.ask", side_effect=["3", "[bold]x", "2"])

        assert prompt_setup_path(console=console) == SetupPath.LOCAL

        assert prompt.call_count == 3
        assert "Invalid choice" in buffer.getvalue()


class TestRunExecutionSetting:
    def test_it_rewrites_the_kit_setting_keeping_the_comments(self, tmp_path: Path) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        kit_text = (get_kit_configs_dir() / "pipelex.toml").read_text(encoding="utf-8")
        pipelex_toml_path.write_text(kit_text, encoding="utf-8")
        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) == RunExecution.LOCAL

        write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=RunExecution.HOSTED)

        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) == RunExecution.HOSTED
        rewritten = pipelex_toml_path.read_text(encoding="utf-8")
        assert rewritten.replace('execution = "hosted"', 'execution = "local"') == kit_text

    def test_it_creates_the_file_or_the_table_when_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing" / "pipelex.toml"
        write_run_execution(pipelex_toml_path=missing, execution=RunExecution.HOSTED)
        assert read_run_execution(pipelex_toml_path=missing) == RunExecution.HOSTED

        without_run = tmp_path / "without_run.toml"
        without_run.write_text("# mine\n[log]\nlevel = 'info'\n", encoding="utf-8")
        write_run_execution(pipelex_toml_path=without_run, execution=RunExecution.LOCAL)
        assert read_run_execution(pipelex_toml_path=without_run) == RunExecution.LOCAL
        assert without_run.read_text(encoding="utf-8").startswith("# mine\n[log]\nlevel = 'info'\n")

    def test_a_run_that_is_not_a_table_is_refused(self, tmp_path: Path) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        pipelex_toml_path.write_text('run = "hosted"\n', encoding="utf-8")

        with pytest.raises(PipelexCLIError):
            write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=RunExecution.HOSTED)

    @pytest.mark.parametrize("content", [None, "", "[run]\n", '[run]\nexecution = "elsewhere"\n', "[run\nbroken", 'run = "hosted"\n'])
    def test_reading_finds_none_when_nothing_valid_is_set(self, tmp_path: Path, content: str | None) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        if content is not None:
            pipelex_toml_path.write_text(content, encoding="utf-8")
        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) is None


class TestEnsurePipelexApiKey:
    @pytest.fixture
    def pipelex_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        home = tmp_path / "pipelex_home"
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
        isolate_pipelex_api_key(monkeypatch)
        return home

    def test_a_key_in_the_environment_skips_the_login(self, mocker: MockerFixture, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        check = mocker.patch("pipelex.cli.commands.login.command.check_pipelex_api_key")
        console, buffer = _console()

        ensure_pipelex_api_key(console=console, interactive=True)

        login.assert_not_called()
        check.assert_not_called()
        assert "already set" in buffer.getvalue()
        assert "plx_sk_test_not_a_secret" not in buffer.getvalue()
        assert not (pipelex_home / ".env").exists()

    def test_a_saved_key_skips_the_login(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        console, _ = _console()

        ensure_pipelex_api_key(console=console, interactive=True)

        login.assert_not_called()

    @pytest.mark.usefixtures("pipelex_home")
    def test_a_key_that_does_not_look_like_one_is_kept_with_a_warning(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "sk-something-else")
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        console, buffer = _console()

        ensure_pipelex_api_key(console=console, interactive=True)

        login.assert_not_called()
        assert "does not look like a Pipelex API key" in buffer.getvalue()

    @pytest.mark.usefixtures("pipelex_home")
    def test_with_no_key_it_signs_in_through_the_browser(self, mocker: MockerFixture) -> None:
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser", return_value=LoginOutcome.SAVED)
        console, buffer = _console()

        ensure_pipelex_api_key(console=console, interactive=True)

        login.assert_called_once_with(console=console)
        assert "No key was saved" not in buffer.getvalue()

    @pytest.mark.usefixtures("pipelex_home")
    def test_a_login_that_saved_nothing_names_pipelex_login(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser", return_value=LoginOutcome.NO_KEY)
        console, buffer = _console()

        ensure_pipelex_api_key(console=console, interactive=True)

        assert "No key was saved" in buffer.getvalue()
        assert "pipelex login" in buffer.getvalue()

    @pytest.mark.usefixtures("pipelex_home")
    def test_with_nobody_to_answer_it_prints_pipelex_login_and_opens_no_browser(self, mocker: MockerFixture) -> None:
        login = mocker.patch("pipelex.cli.commands.init.setup_path.login_with_browser")
        browser_open = mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")
        console, buffer = _console()

        ensure_pipelex_api_key(console=console, interactive=False)

        login.assert_not_called()
        browser_open.assert_not_called()
        assert "Run pipelex login" in buffer.getvalue()
