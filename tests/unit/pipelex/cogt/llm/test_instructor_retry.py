"""Tests for the ``instructor`` schema-re-ask retrying helper.

``make_instructor_schema_retrying`` must confine ``instructor``'s retry to genuine schema re-ask:
a validation failure is retried up to the attempt budget, while a transport error is *not*
retried (so it ends instructor's loop at once for the worker to classify, instead of being
re-run on top of the SDK client's own transport retry).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from instructor.core import ResponseParsingError
from pydantic import BaseModel, ValidationError
from tenacity import RetryError, retry_if_exception_type

from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _Probe(BaseModel):
    value: int


def _make_validation_error() -> ValidationError:
    try:
        _Probe(value="not-an-int")  # type: ignore[arg-type]
    except ValidationError as validation_error:
        return validation_error
    msg = "expected _Probe to reject a non-int value"
    raise AssertionError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestInstructorSchemaRetrying:
    """``make_instructor_schema_retrying`` retries validation failures and only those."""

    async def test_validation_error_is_retried_up_to_stop(self, mocker: MockerFixture) -> None:
        validation_error = _make_validation_error()
        send = mocker.AsyncMock(side_effect=[validation_error, validation_error, validation_error])
        retrying = make_instructor_schema_retrying(max_attempts=3)

        with pytest.raises(RetryError):
            await retrying(send)
        assert send.call_count == 3

    async def test_json_decode_error_is_retried(self, mocker: MockerFixture) -> None:
        decode_error = json.JSONDecodeError("bad", "doc", 0)
        send = mocker.AsyncMock(side_effect=[decode_error, decode_error])
        retrying = make_instructor_schema_retrying(max_attempts=2)

        with pytest.raises(RetryError):
            await retrying(send)
        assert send.call_count == 2

    async def test_unparseable_response_is_retried(self, mocker: MockerFixture) -> None:
        # instructor raises this when a response carries no tool call or no JSON at all, and re-asks it
        parsing_error = ResponseParsingError("No tool call found in the response", mode="TOOLS", raw_response=None)
        send = mocker.AsyncMock(side_effect=[parsing_error, "ok"])
        retrying = make_instructor_schema_retrying(max_attempts=3)

        result: object = await retrying(send)
        assert result == "ok"
        assert send.call_count == 2

    async def test_predicate_matches_what_instructor_itself_reasks(self) -> None:
        # instructor's default loop, the one a bare `max_retries` int builds, re-asks exactly this set.
        # It is private, and it is read here so that an instructor upgrade that changes it fails this test
        from instructor.v2.core.retry import _RETRYABLE_PARSE_ERRORS  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[import-outside-top-level]

        retrying = make_instructor_schema_retrying(max_attempts=2)

        assert isinstance(retrying.retry, retry_if_exception_type)
        exception_types = retrying.retry.exception_types
        assert isinstance(exception_types, tuple)
        assert set(exception_types) == set(_RETRYABLE_PARSE_ERRORS)

    @pytest.mark.parametrize(
        "transport_exc",
        [
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("read timed out"),
        ],
    )
    async def test_transport_error_is_not_retried(self, mocker: MockerFixture, transport_exc: Exception) -> None:
        send = mocker.AsyncMock(side_effect=transport_exc)
        retrying = make_instructor_schema_retrying(max_attempts=3)

        # The predicate excludes transport errors, so the call is tried exactly once and the
        # original exception propagates raw — not wrapped in RetryError, not re-asked.
        with pytest.raises(type(transport_exc)) as exc_info:
            await retrying(send)
        assert send.call_count == 1
        assert exc_info.value is transport_exc

    async def test_validation_error_then_success_returns_value(self, mocker: MockerFixture) -> None:
        send = mocker.AsyncMock(side_effect=[_make_validation_error(), "ok"])
        retrying = make_instructor_schema_retrying(max_attempts=3)

        result: object = await retrying(send)
        assert result == "ok"
        assert send.call_count == 2
