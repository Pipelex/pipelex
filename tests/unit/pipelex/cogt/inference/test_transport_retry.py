"""Tests for the SDK-less Tier 1 transport-retry wrapper.

``request_with_transport_retry`` is the transport-retry floor for inference paths that talk to a
provider over raw ``httpx`` with no retrying SDK in between. It must retry transient transport
failures (connection errors + transient HTTP statuses), honor ``Retry-After``, and — for
submit-style POSTs — withhold retries on failures that may have already landed, so a billable
request is not duplicated.
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

    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(_make_status_error(503), id="server_error_503"),
            pytest.param(_make_status_error(409), id="conflict_409"),
            pytest.param(httpx.ReadTimeout("read timed out"), id="read_timeout"),
            pytest.param(httpx.WriteTimeout("write timed out"), id="write_timeout"),
        ],
    )
    async def test_submit_style_does_not_retry_ambiguous_failures(self, mocker: MockerFixture, failure: httpx.HTTPError) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=failure)

        # A submit-style POST must not be retried once the request may have reached the server —
        # an ambiguous 5xx, a 409 conflict, or a post-send timeout could each duplicate the job.
        with pytest.raises(httpx.HTTPError):
            await request_with_transport_retry(send_request=send, max_retries=3, retry_on_ambiguous_failure=False)
        assert send.call_count == 1

    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(httpx.ConnectError("connection refused"), id="connect_error"),
            pytest.param(httpx.ConnectTimeout("connect timed out"), id="connect_timeout"),
            pytest.param(httpx.PoolTimeout("pool timed out"), id="pool_timeout"),
            pytest.param(_make_status_error(408), id="request_timeout_408"),
            pytest.param(_make_status_error(429), id="rate_limited_429"),
        ],
    )
    async def test_submit_style_retries_failures_that_prove_no_work(self, mocker: MockerFixture, failure: httpx.HTTPError) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        send = mocker.AsyncMock(side_effect=[failure, _make_ok_response()])

        # These failures prove the request never produced billable work — a connection that was
        # never established, or a 408 / 429 rejection — so they are retried even in submit-style.
        response = await request_with_transport_retry(send_request=send, max_retries=3, retry_on_ambiguous_failure=False)
        assert send.call_count == 2
        assert response.status_code == 200

    async def test_naive_retry_after_header_does_not_crash(self, mocker: MockerFixture) -> None:
        mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
        # A "-0000" HTTP-date is a valid RFC date that parses to a *naive* datetime; the wait
        # calculation must treat it as unusable and fall back to backoff, not raise TypeError.
        send = mocker.AsyncMock(
            side_effect=[
                _make_status_error(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 -0000"}),
                _make_ok_response(),
            ]
        )

        response = await request_with_transport_retry(send_request=send, max_retries=3)
        assert send.call_count == 2
        assert response.status_code == 200
