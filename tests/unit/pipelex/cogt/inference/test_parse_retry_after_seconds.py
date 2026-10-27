from __future__ import annotations

from typing import Any

import pytest

from pipelex.cogt.inference.error_classification import parse_retry_after_seconds


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
