"""Tests for the ``InferenceErrorCategory.UNKNOWN`` category.

UNKNOWN exists so unrecognized underlying SDK exceptions don't get silently
mis-categorized as CONTENT. UNKNOWN is non-retryable (we don't know enough
to retry) and surfaces a real "we should add this case" signal in telemetry.
"""

from __future__ import annotations

from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory


class TestInferenceErrorCategoryUnknown:
    """``UNKNOWN`` is a first-class category, not a placeholder."""

    def test_unknown_member_exists_with_string_value(self) -> None:
        assert InferenceErrorCategory.UNKNOWN
        assert str(InferenceErrorCategory.UNKNOWN) == "unknown"

    def test_unknown_is_not_retryable(self) -> None:
        assert InferenceErrorCategory.UNKNOWN.is_retryable is False

    def test_error_report_round_trips_unknown(self) -> None:
        err = CogtError("boom", error_category=InferenceErrorCategory.UNKNOWN)

        report = err.to_error_report()

        assert report.error_category == "unknown"
        assert report.retryable is False
