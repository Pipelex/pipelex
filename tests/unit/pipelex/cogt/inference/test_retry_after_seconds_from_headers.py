from __future__ import annotations

import httpx
import pytest

from pipelex.cogt.inference.error_classification import retry_after_seconds_from_headers


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
            # The milliseconds decide only above zero; for a zero, Pipelex deliberately falls back to the seconds
            pytest.param({"retry-after-ms": "0", "retry-after": "30"}, 30.0, id="zero_milliseconds_leave_the_seconds"),
            pytest.param({"retry-after-ms": "0"}, None, id="zero_milliseconds_alone_read_as_none"),
            pytest.param({"retry-after-ms": "inf"}, None, id="infinite_milliseconds_read_as_none"),
        ],
    )
    def test_reads_the_milliseconds_first(self, headers: dict[str, str] | None, expected_seconds: float | None) -> None:
        """``retry-after-ms``, which the OpenAI and Anthropic SDKs also read first, decides when it is above zero; ``retry-after`` otherwise."""
        assert retry_after_seconds_from_headers(headers=None if headers is None else httpx.Headers(headers)) == expected_seconds
