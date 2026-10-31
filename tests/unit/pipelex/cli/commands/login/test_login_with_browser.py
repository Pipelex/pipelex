"""`pipelex login` opens the app with a fresh `state`, waits for the key, checks it and saves it, never printing it."""

from __future__ import annotations

import stat
from io import StringIO
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
import typer
from rich.console import Console

from pipelex.cli.commands.init.credentials import set_env_file_entries
from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND, PIPELEX_APP_URL_ENV_KEY, LoginOutcome, login_cmd, login_with_browser
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict
from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.urls import URLs
from tests.helpers.login_browser import ACCEPTED, API_URL, TEST_KEY, BrowserStandIn, patch_browser, patch_check, saved_base_url, saved_key
from tests.helpers.pipelex_api_key_env import isolate_pipelex_base_url

DEV_APP_URL = "https://app-dev.test"
DEV_API_URL = "https://api-dev.test"

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

    def test_a_key_the_hosted_api_refuses_is_not_saved_and_is_named_for_revoking(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO
    ) -> None:
        """The app minted the key for this login, so a refused key is a live key nobody holds: the command says to revoke it."""
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=API_URL, http_status=401))

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()
        browser.join()

        assert exc_info.value.exit_code == 1
        assert saved_key(home=pipelex_home) is None
        assert (pipelex_home / ".env").exists() is False
        # Rich wraps long lines at spaces; joining the words back reads the message as written
        printed = " ".join(output.getvalue().split())
        assert "HTTP 401" in printed
        assert "Nothing was saved" in printed
        assert f"The key this login received went unused: revoke it on the Developer page of the Pipelex app ({URLs.app})" in printed
        assert f"the hosted API, {API_URL}, used when {PIPELEX_BASE_URL_ENV_KEY} is not set" in printed
        assert TEST_KEY not in printed

    def test_a_refusal_names_the_env_file_whose_base_url_the_key_was_checked_against(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO
    ) -> None:
        """A base URL saved by an earlier login wins over the shell, so the refusal says which file to change."""
        set_env_file_entries(env_path=pipelex_home / ".env", entries={PIPELEX_BASE_URL_ENV_KEY: DEV_API_URL})
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=DEV_API_URL, http_status=401))

        with pytest.raises(typer.Exit):
            login_cmd()
        browser.join()

        printed = " ".join(output.getvalue().split())
        assert f"the API the {PIPELEX_BASE_URL_ENV_KEY} in {pipelex_home / '.env'} names, {DEV_API_URL}" in printed
        assert f"Pipelex app ({URLs.app})" in printed
        assert "same deployment" in printed
        assert saved_key(home=pipelex_home) is None

    def test_a_refusal_names_the_shell_variable_when_no_env_file_sets_the_base_url(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        isolate_pipelex_base_url(monkeypatch, value=DEV_API_URL)
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=DEV_API_URL, http_status=403))

        with pytest.raises(typer.Exit):
            login_cmd()
        browser.join()

        printed = " ".join(output.getvalue().split())
        assert f"the API {PIPELEX_BASE_URL_ENV_KEY} names, {DEV_API_URL}" in printed
        assert saved_key(home=pipelex_home) is None

    def test_a_checked_base_url_a_env_file_cannot_hold_is_left_out_with_a_warning(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unquotable = "https://api dev.test"
        isolate_pipelex_base_url(monkeypatch, value=unquotable)
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(
            mocker,
            check=ApiKeyCheck(verdict=ApiKeyVerdict.UNCHECKED, base_url=unquotable, reason="the hosted API could not be reached"),
        )

        login_cmd()
        browser.join()

        assert saved_key(home=pipelex_home) == TEST_KEY
        assert saved_base_url(home=pipelex_home) is None
        printed = " ".join(output.getvalue().split())
        assert f"{PIPELEX_BASE_URL_ENV_KEY} could not be saved beside it" in printed
        assert "holds whitespace, a quote, #, $ or a backslash" in printed
        assert f"as {PIPELEX_API_KEY_ENV_KEY} anyway" in printed
        assert TEST_KEY not in printed

    def test_the_base_url_the_shell_exports_is_saved_beside_the_key(
        self, mocker: MockerFixture, pipelex_home: Path, output: StringIO, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A later process without the shell's `PIPELEX_BASE_URL` reads the file alone, so the file must pair the key with the API that checked it."""
        monkeypatch.setenv(PIPELEX_APP_URL_ENV_KEY, DEV_APP_URL)
        isolate_pipelex_base_url(monkeypatch, value=DEV_API_URL)
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=DEV_API_URL, account_email="ada@example.com"))

        login_cmd()
        browser.join()

        assert (pipelex_home / ".env").read_text(encoding="utf-8").splitlines() == [
            f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}",
            f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}",
        ]
        printed = " ".join(output.getvalue().split())
        assert f"beside {PIPELEX_BASE_URL_ENV_KEY} for {DEV_API_URL}" in printed
        assert f"{PIPELEX_BASE_URL_ENV_KEY} is saved with the key" in printed
        assert TEST_KEY not in printed

    def test_a_key_checked_against_the_hosted_api_is_saved_alone(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=HOSTED_API_DEFAULT_BASE_URL, account_email="ada@example.com"))

        login_cmd()
        browser.join()

        assert saved_key(home=pipelex_home) == TEST_KEY
        assert saved_base_url(home=pipelex_home) is None
        assert PIPELEX_BASE_URL_ENV_KEY not in output.getvalue()

    def test_a_key_that_cannot_be_saved_is_named_for_revoking(self, mocker: MockerFixture, pipelex_home: Path, output: StringIO) -> None:
        browser = BrowserStandIn(api_key=TEST_KEY)
        patch_browser(mocker, browser=browser)
        patch_check(mocker, check=ACCEPTED)
        mocker.patch(
            "pipelex.cli.commands.init.credentials.rewrite",
            side_effect=PermissionError(13, "Permission denied", str(pipelex_home / ".env")),
        )

        with pytest.raises(typer.Exit) as exc_info:
            login_cmd()
        browser.join()

        assert exc_info.value.exit_code == 1
        printed = " ".join(output.getvalue().split())
        assert "Permission denied" in printed
        assert f"revoke it on the Developer page of the Pipelex app ({URLs.app})" in printed
        assert TEST_KEY not in printed

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
        # The key was meant for the API it could not reach, as the workshop's login pairs an unchecked key too.
        assert saved_base_url(home=pipelex_home) == API_URL
        # Rich wraps long lines at spaces; joining the words back reads the message as written
        printed = " ".join(output.getvalue().split())
        assert "Could not check the key" in printed
        assert "could not be reached" in printed
        assert f"as {PIPELEX_API_KEY_ENV_KEY}, beside {PIPELEX_BASE_URL_ENV_KEY} for {API_URL} anyway" in printed
        assert f"{PIPELEX_BASE_URL_ENV_KEY} is saved with the key" in printed

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
