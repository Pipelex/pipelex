from __future__ import annotations

from typing import Any

import httpx
import pytest

from pipelex.cogt.inference.error_classification import parse_retry_after_seconds, retry_after_seconds_from_headers


class TestParseRetryAfterSeconds:
    @pytest.mark.parametrize(
        ("header_value", "expected_seconds"),
        [
            pytest.param(None, None, id="absent"),
            pytest.param("12", 12.0, id="integer_seconds"),
            pytest.param("12.5", 12.5, id="fractional_seconds"),
            pytest.param("0", 0.0, id="zero"),
            pytest.param(7, 7.0, id="number_not_string"),
            pytest.param("inf", None, id="infinity"),
            pytest.param("-inf", None, id="negative_infinity"),
            pytest.param("nan", None, id="not_a_number"),
            pytest.param("1e999", None, id="overflows_to_infinity"),
            pytest.param("-5", None, id="negative"),
            pytest.param("soon", None, id="neither_number_nor_date"),
            pytest.param("Wed, 21 Oct 2015 07:28:00 GMT", 0.0, id="date_in_the_past"),
        ],
    )
    def test_reads_only_a_delay_the_spec_allows(self, header_value: Any, expected_seconds: float | None) -> None:
        """A Retry-After value is a non-negative finite number of seconds or an HTTP-date; anything else reads as no delay."""
        assert parse_retry_after_seconds(header_value) == expected_seconds


class TestRetryAfterSecondsFromHeaders:
    @pytest.mark.parametrize(
        ("headers", "expected_seconds"),
        [
            pytest.param(None, None, id="no_headers"),
            pytest.param({}, None, id="neither_header"),
            pytest.param({"retry-after": "2"}, 2.0, id="seconds_alone"),
            pytest.param({"retry-after-ms": "1500"}, 1.5, id="milliseconds_alone"),
            # Azure OpenAI's shape: both, the milliseconds the more precise
            pytest.param({"retry-after-ms": "4500", "retry-after": "5"}, 4.5, id="milliseconds_before_seconds"),
            pytest.param({"Retry-After-Ms": "250"}, 0.25, id="any_case"),
            pytest.param({"retry-after-ms": "soon", "retry-after": "3"}, 3.0, id="unreadable_milliseconds_leave_the_seconds"),
            pytest.param({"retry-after-ms": "-5", "retry-after": "3"}, 3.0, id="negative_milliseconds_leave_the_seconds"),
            # As in the OpenAI SDK, the milliseconds decide only above zero
            pytest.param({"retry-after-ms": "0", "retry-after": "30"}, 30.0, id="zero_milliseconds_leave_the_seconds"),
            pytest.param({"retry-after-ms": "0"}, None, id="zero_milliseconds_alone_read_as_none"),
            pytest.param({"retry-after-ms": "inf"}, None, id="infinite_milliseconds_read_as_none"),
        ],
    )
    def test_reads_the_milliseconds_first(self, headers: dict[str, str] | None, expected_seconds: float | None) -> None:
        """``retry-after-ms`` decides when it holds a delay above zero, as the OpenAI and Anthropic SDKs read it; ``retry-after`` otherwise."""
        assert retry_after_seconds_from_headers(headers=None if headers is None else httpx.Headers(headers)) == expected_seconds
