"""The loopback listener keeps a key only from a callback carrying the `state` its own login generated."""

from __future__ import annotations

import http.client
import threading
from urllib.parse import urlencode

import pytest

from pipelex.cli.commands.login.loopback import CALLBACK_PATH, LOOPBACK_HOST, CallbackRefusal, LoopbackListener

TEST_KEY = "plx_sk_test_not_a_secret"


def _get(*, port: int, path: str) -> int:
    """Send one GET to the listener and return the status it answered."""
    connection = http.client.HTTPConnection(LOOPBACK_HOST, port, timeout=5)
    try:
        connection.request("GET", path)
        return connection.getresponse().status
    finally:
        connection.close()


def _callback_path(*, api_key: str | None, state: str | None) -> str:
    params = {name: value for name, value in (("api_key", api_key), ("state", state)) if value is not None}
    return f"{CALLBACK_PATH}?{urlencode(params)}"


class _BrowserStandIn:
    """Sends requests to the listener from another thread, as the browser does while the listener waits."""

    def __init__(self, *, port: int, paths: list[str]) -> None:
        self.statuses: list[int] = []
        self._port = port
        self._paths = paths
        self._thread = threading.Thread(target=self._send_all, daemon=True)

    def _send_all(self) -> None:
        for path in self._paths:
            self.statuses.append(_get(port=self._port, path=path))

    def start(self) -> None:
        self._thread.start()

    def join(self) -> None:
        self._thread.join(timeout=10)


class TestLoopbackListener:
    def test_it_binds_the_loopback_address_and_generates_a_fresh_state(self) -> None:
        with LoopbackListener() as first, LoopbackListener() as second:
            assert first.port > 0
            assert first.state != second.state
            assert len(first.state) >= 32

    def test_a_callback_with_the_matching_state_hands_over_the_key(self) -> None:
        with LoopbackListener() as listener:
            browser = _BrowserStandIn(port=listener.port, paths=[_callback_path(api_key=TEST_KEY, state=listener.state)])
            browser.start()
            api_key = listener.wait_for_api_key(timeout_seconds=10)
            browser.join()

        assert api_key == TEST_KEY
        assert browser.statuses == [200]

    @pytest.mark.parametrize("state", ["not-the-state", None, ""])
    def test_a_callback_with_a_wrong_or_missing_state_is_refused_and_the_wait_goes_on(self, state: str | None) -> None:
        refusals: list[CallbackRefusal] = []
        with LoopbackListener() as listener:
            browser = _BrowserStandIn(
                port=listener.port,
                paths=[
                    _callback_path(api_key="plx_sk_from_another_page", state=state),
                    _callback_path(api_key=TEST_KEY, state=listener.state),
                ],
            )
            browser.start()
            api_key = listener.wait_for_api_key(timeout_seconds=10, on_refusal=refusals.append)
            browser.join()

        assert api_key == TEST_KEY
        assert browser.statuses == [400, 200]
        assert refusals == [CallbackRefusal.STATE_MISMATCH]

    def test_a_callback_carrying_the_state_twice_is_refused(self) -> None:
        """Two `state` values cannot both be this login's, whichever one matches."""
        with LoopbackListener() as listener:
            path = f"{CALLBACK_PATH}?{urlencode([('api_key', TEST_KEY), ('state', listener.state), ('state', 'other')])}"
            browser = _BrowserStandIn(port=listener.port, paths=[path])
            browser.start()
            api_key = listener.wait_for_api_key(timeout_seconds=2)
            browser.join()

        assert api_key is None
        assert browser.statuses == [400]

    def test_a_callback_without_a_key_is_refused_and_the_wait_goes_on(self) -> None:
        refusals: list[CallbackRefusal] = []
        with LoopbackListener() as listener:
            browser = _BrowserStandIn(
                port=listener.port,
                paths=[_callback_path(api_key=None, state=listener.state), _callback_path(api_key=TEST_KEY, state=listener.state)],
            )
            browser.start()
            api_key = listener.wait_for_api_key(timeout_seconds=10, on_refusal=refusals.append)
            browser.join()

        assert api_key == TEST_KEY
        assert browser.statuses == [400, 200]
        assert refusals == [CallbackRefusal.NO_API_KEY]

    def test_other_paths_are_ignored(self) -> None:
        with LoopbackListener() as listener:
            browser = _BrowserStandIn(
                port=listener.port,
                paths=[
                    f"/other?{urlencode({'api_key': TEST_KEY, 'state': listener.state})}",
                    _callback_path(api_key=TEST_KEY, state=listener.state),
                ],
            )
            browser.start()
            api_key = listener.wait_for_api_key(timeout_seconds=10)
            browser.join()

        assert api_key == TEST_KEY
        assert browser.statuses == [404, 200]

    def test_no_callback_in_time_returns_none(self) -> None:
        with LoopbackListener() as listener:
            assert listener.wait_for_api_key(timeout_seconds=0.2) is None
