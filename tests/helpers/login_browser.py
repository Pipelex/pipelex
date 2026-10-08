"""Stand-ins for the browser and the key check of `pipelex login`, so a login test opens nothing and calls no API."""

from __future__ import annotations

import http.client
import threading
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlsplit

from pipelex.cli.commands.init.credentials import read_env_file_value
from pipelex.cli.commands.login.loopback import CALLBACK_PATH, LOOPBACK_HOST
from pipelex.hosted.api_key_check import ApiKeyCheck, ApiKeyVerdict
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

#: A value shaped like a Pipelex API key, which no hosted API knows.
TEST_KEY = "plx_sk_test_not_a_secret"
API_URL = "https://api.test"
ACCEPTED = ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=API_URL, account_email="ada@example.com")


class BrowserStandIn:
    """Stands in for `webbrowser.open`: records the URL and, when told to, sends the app's callback to the listener."""

    def __init__(self, *, api_key: str | None, echo_state: bool = True, opens: bool = True) -> None:
        self.opened_urls: list[str] = []
        self._api_key = api_key
        self._echo_state = echo_state
        self._opens = opens
        self._threads: list[threading.Thread] = []

    def open(self, url: str) -> bool:
        self.opened_urls.append(url)
        if self._api_key is None:
            return self._opens
        query = parse_qs(urlsplit(url).query)
        port = int(query["callback_port"][0])
        state = query["state"][0] if self._echo_state else "forged-state"
        thread = threading.Thread(target=self._call_back, kwargs={"port": port, "state": state}, daemon=True)
        thread.start()
        self._threads.append(thread)
        return self._opens

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


def patch_browser(mocker: MockerFixture, *, browser: BrowserStandIn) -> None:
    mocker.patch("pipelex.cli.commands.login.command.webbrowser.open", side_effect=browser.open)


def patch_check(mocker: MockerFixture, *, check: ApiKeyCheck) -> MockType:
    return mocker.patch("pipelex.cli.commands.login.command.check_pipelex_api_key", return_value=check)


def saved_key(*, home: Path) -> str | None:
    """The key saved in a home configuration directory's `.env`."""
    return read_env_file_value(env_path=home / ".env", key=PIPELEX_API_KEY_ENV_KEY)
