"""`pipelex login` opens the app with a fresh `state`, waits for the key, checks it and saves it, never printing it."""

from __future__ import annotations

import stat
from io import StringIO
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND, PIPELEX_APP_URL_ENV_KEY, LoginOutcome, login_cmd, login_with_browser
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict
from tests.helpers.login_browser import ACCEPTED, API_URL, TEST_KEY, BrowserStandIn, patch_browser, patch_check, saved_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestLoginWithBrowser:
    def test_a_checked_key_is_saved_and_never_printed(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        check = patch_check(mocker, check=ACCEPTED)

        login_cmd()
        browser.join()

        check.assert_called_once_with(api_key=TEST_KEY)
        assert saved_key(home=pipelex_home) == TEST_KEY
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
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ACCEPTED)

        login_cmd()
        browser.join()

        parts = urlsplit(browser.opened_urls[0])
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://app-dev.pipelex.com/auth/cli"
        assert set(parse_qs(parts.query)) == {"callback_port", "state"}
        assert saved_key(home=pipelex_home) == TEST_KEY

    def test_a_key_the_hosted_api_refuses_is_not_saved(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=API_URL, http_status=401))

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()
        browser.join()

        assert exc_info.value.exit_code == 1
        assert saved_key(home=pipelex_home) is None
        assert "HTTP 401" in output.getvalue()
        assert TEST_KEY not in output.getvalue()

    def test_a_key_that_could_not_be_checked_is_saved_with_a_warning(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(
            mocker,
            check=ApiKeyCheck(verdict=ApiKeyVerdict.UNCHECKED, base_url=API_URL, reason="the hosted API at https://api.test could not be reached"),
        )

        login_cmd()
        browser.join()

        assert saved_key(home=pipelex_home) == TEST_KEY
        assert "Could not check the key" in output.getvalue()
        assert "could not be reached" in output.getvalue()

    def test_a_value_that_is_not_a_pipelex_api_key_is_refused_unchecked(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key="sk-not-a-pipelex-key")
        patch_browser(mocker, browser=browser)
        check = patch_check(mocker, check=ACCEPTED)

        with pytest.raises(typer.Exit):
            login_cmd()
        browser.join()

        check.assert_not_called()
        assert saved_key(home=pipelex_home) is None
        assert "plx_sk_" in output.getvalue()

    def test_a_callback_with_a_forged_state_is_refused_and_the_login_times_out(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        buffer = StringIO()
        console = Console(file=buffer, width=200)
        browser = BrowserStandIn(api_key=TEST_KEY, echo_state=False)
        patch_browser(mocker, browser=browser)
        check = patch_check(mocker, check=ACCEPTED)

        outcome = login_with_browser(console=console, timeout_seconds=1)
        browser.join()

        assert outcome == LoginOutcome.NO_KEY
        check.assert_not_called()
        assert saved_key(home=pipelex_home) is None
        assert "did not come from the page this login opened" in buffer.getvalue()

    def test_the_timeout_exits_1_and_names_paste(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        patch_browser(mocker, browser=BrowserStandIn(api_key=None))
        mocker.patch("pipelex.cli.commands.login.command.LOGIN_TIMEOUT_SECONDS", 0.2)

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()

        assert exc_info.value.exit_code == 1
        assert LOGIN_PASTE_COMMAND in output.getvalue()
        assert saved_key(home=pipelex_home) is None

    @pytest.mark.usefixtures("pipelex_home")
    def test_a_browser_that_does_not_open_says_so_at_once_and_names_paste(self, mocker: MockerFixture) -> None:
        buffer = StringIO()
        console = Console(file=buffer, width=200)
        browser = BrowserStandIn(api_key=None, opens=False)
        patch_browser(mocker, browser=browser)

        outcome = login_with_browser(console=console, timeout_seconds=0.3)

        assert outcome == LoginOutcome.NO_KEY
        printed = buffer.getvalue()
        assert "No browser could be opened" in printed
        timeout_at = printed.index("No key arrived")
        assert printed.index("No browser could be opened") < timeout_at
        assert printed.index(LOGIN_PASTE_COMMAND) < timeout_at
        assert printed.index(browser.opened_urls[0]) < timeout_at

    @pytest.mark.usefixtures("pipelex_home")
    def test_an_invalid_pipelex_app_url_opens_nothing(
        self,
        mocker: MockerFixture,
        output: StringIO,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, "https://app.test/auth/cli")
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)

        with pytest.raises(typer.Exit):
            login_cmd()

        assert browser.opened_urls == []
        assert PIPELEX_APP_URL_ENV_KEY in output.getvalue()
