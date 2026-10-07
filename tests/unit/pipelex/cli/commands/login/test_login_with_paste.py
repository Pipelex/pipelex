"""`pipelex login --paste` takes a key from a hidden prompt through the same check and save as the browser flow."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.login.command import login_cmd
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from tests.helpers.login_browser import ACCEPTED, API_URL, TEST_KEY, patch_check, saved_key

if TYPE_CHECKING:
    from io import StringIO

    from pytest_mock import MockerFixture


class TestLoginWithPaste:
    def test_a_pasted_key_takes_the_same_check_and_save(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        prompt = mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=f"  {TEST_KEY}\n")
        check = patch_check(mocker, check=ACCEPTED)
        browser_open = mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")

        login_cmd(paste=True)

        assert prompt.call_args.kwargs["password"] is True
        check.assert_called_once_with(api_key=TEST_KEY)
        browser_open.assert_not_called()
        assert saved_key(home=pipelex_home) == TEST_KEY
        assert TEST_KEY not in output.getvalue()

    def test_a_pasted_key_the_hosted_api_refuses_is_not_saved(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=TEST_KEY)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=API_URL, http_status=403))

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        assert saved_key(home=pipelex_home) is None
        assert "HTTP 403" in output.getvalue()

    def test_a_working_directory_env_that_would_shadow_the_saved_key_is_named(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO
    ) -> None:
        Path(".env").write_text(f"{PIPELEX_API_KEY_ENV_KEY}=\n", encoding="utf-8")
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=TEST_KEY)
        patch_check(mocker, check=ACCEPTED)

        login_cmd(paste=True)

        assert saved_key(home=pipelex_home) == TEST_KEY
        printed = output.getvalue()
        assert str(Path(".env").resolve()) in printed.replace("\n", "")
        assert "remove" in printed.lower()
        assert TEST_KEY not in printed

    @pytest.mark.parametrize("answer", ["", "   "])
    def test_nothing_pasted_saves_nothing(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO, answer: str) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=answer)
        check = patch_check(mocker, check=ACCEPTED)

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        check.assert_not_called()
        assert saved_key(home=pipelex_home) is None
        assert "No key was entered" in output.getvalue()

    @pytest.mark.usefixtures("output")
    def test_no_stdin_saves_nothing(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", side_effect=EOFError)

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        assert saved_key(home=pipelex_home) is None
