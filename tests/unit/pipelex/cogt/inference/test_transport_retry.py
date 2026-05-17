"""Tests for the SDK-less Tier 1 transport-retry wrapper.

``request_with_transport_retry`` is the transport-retry floor for inference paths that talk to a
provider over raw ``httpx`` with no retrying SDK in between. It must retry transient transport
failures (connection errors + transient HTTP statuses), honor ``Retry-After``, and — for
submit-style POSTs — refuse to retry an ambiguous 5xx so a landed request is not duplicated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from pipelex.cogt.inference.transport_retry import request_with_transport_retry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_status_error(status_code: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/generate")
    response = httpx.Response(status_code=status_code, request=request, headers=headers or {})
    return httpx.HTTPStatusError("error", request=request, response=response)


def _make_ok_response() -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/generate")
    return httpx.Response(status_code=200, request=request, json={"ok": True})


@pytest.mark.asyncio(loop_scope="class")
class TestRequestWithTransportRetry:
    """``request_with_transport_retry`` retries transient failures and honors the idempotency caveat."""

    async def test_retries_transient_status_then_succeeds(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=[_make_status_error(503), _make_status_error(503), _make_ok_response()])

        response = await request_with_transport_retry(send_request=send, max_retries=3)
        assert send.call_count == 3
        assert response.status_code == 200

    async def test_retries_connection_error_then_succeeds(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=[httpx.ConnectError("connection refused"), _make_ok_response()])

        response = await request_with_transport_retry(send_request=send, max_retries=3)
        assert send.call_count == 2
        assert response.status_code == 200

    async def test_honors_retry_after_header(self, mocker: MockerFixture) -> None:
        sleep_mock = mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=[_make_status_error(429, headers={"Retry-After": "5"}), _make_ok_response()])

        await request_with_transport_retry(send_request=send, max_retries=3)
        sleep_mock.assert_awaited_once_with(5.0)

    async def test_exhausts_budget_and_reraises_raw(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(httpx.ConnectError):
            await request_with_transport_retry(send_request=send, max_retries=2)
        # max_retries=2 → initial attempt + 2 retries.
        assert send.call_count == 3

    async def test_non_transient_status_is_not_retried(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=_make_status_error(400))

        with pytest.raises(httpx.HTTPStatusError):
            await request_with_transport_retry(send_request=send, max_retries=3)
        assert send.call_count == 1

    async def test_submit_style_not_retried_on_ambiguous_server_error(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=_make_status_error(503))

        # A submit-style POST may have already landed when a 5xx comes back — retrying it would
        # duplicate the job, so retry_on_ambiguous_failure=False must stop after one attempt.
        with pytest.raises(httpx.HTTPStatusError):
            await request_with_transport_retry(send_request=send, max_retries=3, retry_on_ambiguous_failure=False)
        assert send.call_count == 1

    async def test_submit_style_still_retries_connection_error(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=[httpx.ConnectError("connection refused"), _make_ok_response()])

        # A connection error proves the request did not land, so it is retried even in submit-style.
        response = await request_with_transport_retry(send_request=send, max_retries=3, retry_on_ambiguous_failure=False)
        assert send.call_count == 2
        assert response.status_code == 200
