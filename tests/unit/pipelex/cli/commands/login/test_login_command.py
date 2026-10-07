"""`pipelex login` opens the app with a fresh `state`, waits for the key, checks it and saves it, never printing it."""

from __future__ import annotations

import http.client
import stat
import threading
from io import StringIO
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.init.credentials import read_env_file_value
from pipelex.cli.commands.login.command import (
    LOGIN_PASTE_COMMAND,
    PIPELEX_APP_URL_ENV_KEY,
    LoginOutcome,
    build_cli_auth_url,
    login_cmd,
    login_with_browser,
    resolve_app_origin,
)
from pipelex.cli.commands.login.loopback import CALLBACK_PATH, LOOPBACK_HOST
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

TEST_KEY = "plx_sk_test_not_a_secret"
API_URL = "https://api.test"


class _Browser:
    """Stands in for `webbrowser.open`: records the URL and, when told to, sends the app's callback to the listener."""

    def __init__(self, *, api_key: str | None, echo_state: bool = True) -> None:
        self.opened_urls: list[str] = []
        self._api_key = api_key
        self._echo_state = echo_state
        self._threads: list[threading.Thread] = []

    def open(self, url: str) -> bool:
        self.opened_urls.append(url)
        if self._api_key is None:
            return True
        query = parse_qs(urlsplit(url).query)
        port = int(query["callback_port"][0])
        state = query["state"][0] if self._echo_state else "forged-state"
        thread = threading.Thread(target=self._call_back, kwargs={"port": port, "state": state}, daemon=True)
        thread.start()
        self._threads.append(thread)
        return True

    def _call_back(self, *, port: int, state: str) -> None:
        connection = http.client.HTTPConnection(LOOPBACK_HOST, port, timeout=5)
        try:
            connection.request("GET", f"{CALLBACK_PATH}?{urlencode({'api_key': self._api_key, 'state': state})}")
            connection.getresponse().read()
        finally:
            connection.close()

    def join(self) -> None:
        for thread in self._threads:
            thread.join(timeout=10)


@pytest.fixture
def pipelex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "pipelex_home"
    monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
    monkeypatch.delenv(PIPELEX_APP_URL_ENV_KEY, raising=False)
    isolate_pipelex_api_key(monkeypatch)
    return home


@pytest.fixture
def output(mocker: MockerFixture) -> StringIO:
    """What the command prints."""
    buffer = StringIO()
    mocker.patch("pipelex.cli.commands.login.command.get_console", return_value=Console(file=buffer, width=200))
    return buffer


def _patch_browser(mocker: MockerFixture, *, browser: _Browser) -> None:
    mocker.patch("pipelex.cli.commands.login.command.webbrowser.open", side_effect=browser.open)


def _patch_check(mocker: MockerFixture, *, check: ApiKeyCheck) -> MockType:
    return mocker.patch("pipelex.cli.commands.login.command.check_pipelex_api_key", return_value=check)


def _saved_key(home: Path) -> str | None:
    return read_env_file_value(env_path=home / ".env", key=PIPELEX_API_KEY_ENV_KEY)


ACCEPTED = ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=API_URL, account_email="ada@example.com")


class TestAppOrigin:
    def test_the_default_is_the_pipelex_app(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PIPELEX_APP_URL_ENV_KEY, raising=False)
        assert resolve_app_origin() == "https://app.pipelex.com"

    @pytest.mark.parametrize("value", ["https://app-dev.pipelex.com", "https://app-dev.pipelex.com/", "http://localhost:3000"])
    def test_pipelex_app_url_names_another_app(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, value)
        assert resolve_app_origin() == value.rstrip("/")

    @pytest.mark.parametrize(
        "value", ["", "app.pipelex.com", "ftp://app.test", "https://app.test/auth", "https://user:secret@app.test", "https://app.test?x=1"]
    )
    def test_a_value_that_is_not_an_origin_is_refused_without_quoting_credentials(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, value)
        with pytest.raises(PipelexCLIError) as exc_info:
            resolve_app_origin()
        assert PIPELEX_APP_URL_ENV_KEY in exc_info.value.message
        assert "secret" not in exc_info.value.message

    def test_the_auth_url_names_the_port_and_the_state(self) -> None:
        url = build_cli_auth_url(app_origin="https://app-dev.pipelex.com", callback_port=51234, state="abc")
        assert url == "https://app-dev.pipelex.com/auth/cli?callback_port=51234&state=abc"


class TestLoginWithBrowser:
    def test_a_checked_key_is_saved_and_never_printed(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = _Browser(api_key=TEST_KEY)
        _patch_browser(mocker, browser=browser)
        check = _patch_check(mocker, check=ACCEPTED)

        login_cmd()
        browser.join()

        check.assert_called_once_with(api_key=TEST_KEY)
        assert _saved_key(pipelex_home) == TEST_KEY
        assert stat.S_IMODE((pipelex_home / ".env").stat().st_mode) == 0o600
        printed = output.getvalue()
        assert TEST_KEY not in printed
        assert "ada@example.com" in printed
        assert len(browser.opened_urls) == 1
        assert browser.opened_urls[0] in printed

    @pytest.mark.usefixtures("output")
    def test_it_opens_the_app_pipelex_app_url_names(
        self,
        mocker: MockerFixture,
        pipelex_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, "https://app-dev.pipelex.com")
        browser = _Browser(api_key=TEST_KEY)
        _patch_browser(mocker, browser=browser)
        _patch_check(mocker, check=ACCEPTED)

        login_cmd()
        browser.join()

        parts = urlsplit(browser.opened_urls[0])
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://app-dev.pipelex.com/auth/cli"
        assert set(parse_qs(parts.query)) == {"callback_port", "state"}
        assert _saved_key(pipelex_home) == TEST_KEY

    def test_a_key_the_hosted_api_refuses_is_not_saved(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = _Browser(api_key=TEST_KEY)
        _patch_browser(mocker, browser=browser)
        _patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=API_URL, http_status=401))

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()
        browser.join()

        assert exc_info.value.exit_code == 1
        assert _saved_key(pipelex_home) is None
        assert "HTTP 401" in output.getvalue()
        assert TEST_KEY not in output.getvalue()

    def test_a_key_that_could_not_be_checked_is_saved_with_a_warning(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = _Browser(api_key=TEST_KEY)
        _patch_browser(mocker, browser=browser)
        _patch_check(
            mocker,
            check=ApiKeyCheck(verdict=ApiKeyVerdict.UNCHECKED, base_url=API_URL, reason="the hosted API at https://api.test could not be reached"),
        )

        login_cmd()
        browser.join()

        assert _saved_key(pipelex_home) == TEST_KEY
        assert "Could not check the key" in output.getvalue()
        assert "could not be reached" in output.getvalue()

    def test_a_value_that_is_not_a_pipelex_api_key_is_refused_unchecked(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = _Browser(api_key="sk-not-a-pipelex-key")
        _patch_browser(mocker, browser=browser)
        check = _patch_check(mocker, check=ACCEPTED)

        with pytest.raises(typer.Exit):
            login_cmd()
        browser.join()

        check.assert_not_called()
        assert _saved_key(pipelex_home) is None
        assert "plx_sk_" in output.getvalue()

    def test_a_callback_with_a_forged_state_is_refused_and_the_login_times_out(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        buffer = StringIO()
        console = Console(file=buffer, width=200)
        browser = _Browser(api_key=TEST_KEY, echo_state=False)
        _patch_browser(mocker, browser=browser)
        check = _patch_check(mocker, check=ACCEPTED)

        outcome = login_with_browser(console=console, timeout_seconds=1)
        browser.join()

        assert outcome == LoginOutcome.NO_KEY
        check.assert_not_called()
        assert _saved_key(pipelex_home) is None
        assert "did not come from the page this login opened" in buffer.getvalue()

    def test_the_timeout_exits_1_and_names_paste(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        _patch_browser(mocker, browser=_Browser(api_key=None))
        mocker.patch("pipelex.cli.commands.login.command.LOGIN_TIMEOUT_SECONDS", 0.2)

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()

        assert exc_info.value.exit_code == 1
        assert LOGIN_PASTE_COMMAND in output.getvalue()
        assert _saved_key(pipelex_home) is None

    @pytest.mark.usefixtures("pipelex_home")
    def test_an_invalid_pipelex_app_url_opens_nothing(
        self,
        mocker: MockerFixture,
        output: StringIO,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, "https://app.test/auth/cli")
        browser = _Browser(api_key=TEST_KEY)
        _patch_browser(mocker, browser=browser)

        with pytest.raises(typer.Exit):
            login_cmd()

        assert browser.opened_urls == []
        assert PIPELEX_APP_URL_ENV_KEY in output.getvalue()


class TestLoginWithPaste:
    def test_a_pasted_key_takes_the_same_check_and_save(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        prompt = mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=f"  {TEST_KEY}\n")
        check = _patch_check(mocker, check=ACCEPTED)
        browser_open = mocker.patch("pipelex.cli.commands.login.command.webbrowser.open")

        login_cmd(paste=True)

        assert prompt.call_args.kwargs["password"] is True
        check.assert_called_once_with(api_key=TEST_KEY)
        browser_open.assert_not_called()
        assert _saved_key(pipelex_home) == TEST_KEY
        assert TEST_KEY not in output.getvalue()

    def test_a_pasted_key_the_hosted_api_refuses_is_not_saved(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=TEST_KEY)
        _patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=API_URL, http_status=403))

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        assert _saved_key(pipelex_home) is None
        assert "HTTP 403" in output.getvalue()

    @pytest.mark.parametrize("answer", ["", "   "])
    def test_nothing_pasted_saves_nothing(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO, answer: str) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", return_value=answer)
        check = _patch_check(mocker, check=ACCEPTED)

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        check.assert_not_called()
        assert _saved_key(pipelex_home) is None
        assert "No key was entered" in output.getvalue()

    @pytest.mark.usefixtures("output")
    def test_no_stdin_saves_nothing(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        mocker.patch("pipelex.cli.commands.login.command.Prompt.ask", side_effect=EOFError)

        with pytest.raises(typer.Exit):
            login_cmd(paste=True)

        assert _saved_key(pipelex_home) is None
