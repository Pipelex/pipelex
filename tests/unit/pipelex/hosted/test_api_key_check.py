"""A key is checked with `GET /v1/me`: accepted, refused by a 401 or a 403, or left unchecked by anything else."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from pipelex_sdk.client import PipelexAPIClient
from typing_extensions import override

from pipelex.hosted.api_key_check import ApiKeyVerdict, check_pipelex_api_key, is_well_formed_pipelex_api_key
from pipelex.hosted.client_factory import PIPELEX_BASE_URL_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

API_URL = "https://api.test"
TEST_KEY = "plx_sk_test_not_a_secret"
PROFILE = {"email": "ada@example.com", "user_id": "u_1", "full_name": "Ada"}


def _html_page(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>not an API</html>", request=request)


def _unexpected_json(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"unexpected": True}, request=request)


class _MockTransportClient(PipelexAPIClient):
    """The real client, its HTTP answered by a handler instead of the network."""

    def __init__(self, *, api_key: str | None, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        super().__init__(api_key=api_key, base_url=API_URL)
        self._handler = handler

    @override
    def start_client(self) -> PipelexAPIClient:
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=httpx.MockTransport(self._handler),
        )
        return self


class _Requests:
    """The requests the hosted API stand-in received."""

    def __init__(self) -> None:
        self.received: list[httpx.Request] = []


def _patch_client(mocker: MockerFixture, *, handler: Callable[[httpx.Request], httpx.Response]) -> _Requests:
    requests = _Requests()

    def _recording_handler(request: httpx.Request) -> httpx.Response:
        requests.received.append(request)
        return handler(request)

    def _make(*, base_url: str | None = None, api_key: str | None = None) -> PipelexAPIClient:
        assert base_url is None
        return _MockTransportClient(api_key=api_key, handler=_recording_handler)

    mocker.patch("pipelex.hosted.api_key_check.make_hosted_client", side_effect=_make)
    return requests


def _problem(*, status: int) -> Callable[[httpx.Request], httpx.Response]:
    body = json.dumps({"type": "about:blank", "title": "Refused", "status": status, "detail": "Invalid API key"})

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode(), headers={"content-type": "application/problem+json"}, request=request)

    return _handler


class TestPipelexApiKeyFormat:
    @pytest.mark.parametrize("api_key", [TEST_KEY, "plx_sk_0123abcdef", "plx_sk_a.b~c-d_e"])
    def test_a_pipelex_api_key_is_well_formed(self, api_key: str) -> None:
        assert is_well_formed_pipelex_api_key(api_key=api_key)

    @pytest.mark.parametrize("api_key", ["", "plx_sk_", "sk-openai", "plx_pk_abc", "plx_sk_abc def", "plx_sk_abc'", "plx_sk_abc#x", " plx_sk_abc"])
    def test_anything_else_is_not(self, api_key: str) -> None:
        assert not is_well_formed_pipelex_api_key(api_key=api_key)


class TestCheckPipelexApiKey:
    @pytest.fixture(autouse=True)
    def no_hosted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        isolate_pipelex_api_key(monkeypatch, value="plx_sk_the_environment_key")
        monkeypatch.delenv(PIPELEX_BASE_URL_ENV_KEY, raising=False)

    def test_an_accepted_key_names_its_account_and_is_the_one_sent(self, mocker: MockerFixture) -> None:
        requests = _patch_client(mocker, handler=lambda request: httpx.Response(200, json=PROFILE, request=request))

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.ACCEPTED
        assert check.account_email == "ada@example.com"
        assert check.base_url == API_URL
        assert [request.url.path for request in requests.received] == ["/v1/me"]
        assert requests.received[0].headers["Authorization"] == f"Bearer {TEST_KEY}"

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_401_or_a_403_refuses_the_key(self, mocker: MockerFixture, status: int) -> None:
        _patch_client(mocker, handler=_problem(status=status))

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.REFUSED
        assert check.http_status == status

    @pytest.mark.parametrize("status", [404, 429, 500, 503])
    def test_another_status_leaves_the_key_unchecked(self, mocker: MockerFixture, status: int) -> None:
        _patch_client(mocker, handler=_problem(status=status))

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.UNCHECKED
        assert check.http_status == status
        assert check.reason is not None
        assert str(status) in check.reason

    def test_an_unreachable_api_leaves_the_key_unchecked(self, mocker: MockerFixture) -> None:
        def _unreachable(request: httpx.Request) -> httpx.Response:
            msg = "connection refused"
            raise httpx.ConnectError(msg, request=request)

        _patch_client(mocker, handler=_unreachable)

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.UNCHECKED
        assert check.reason is not None
        assert "could not be reached" in check.reason
        assert TEST_KEY not in check.reason

    @pytest.mark.parametrize("response_factory", [_html_page, _unexpected_json])
    def test_an_answer_that_is_not_a_profile_leaves_the_key_unchecked(
        self,
        mocker: MockerFixture,
        response_factory: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        _patch_client(mocker, handler=response_factory)

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.UNCHECKED

    def test_a_base_url_that_is_not_an_origin_leaves_the_key_unchecked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, "https://api.test/v1")

        check = check_pipelex_api_key(api_key=TEST_KEY)

        assert check.verdict == ApiKeyVerdict.UNCHECKED
        assert check.reason is not None
        assert PIPELEX_BASE_URL_ENV_KEY in check.reason
