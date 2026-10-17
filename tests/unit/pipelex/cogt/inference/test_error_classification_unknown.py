"""Tests for the ``InferenceErrorCategory.UNKNOWN`` category.

UNKNOWN exists so unrecognized underlying SDK exceptions don't get silently
mis-categorized as CONTENT. UNKNOWN is non-retryable (we don't know enough
to retry) and surfaces a real "we should add this case" signal in telemetry.
"""

from __future__ import annotations

from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, find_inference_error_category_in_chain
from pipelex.errors.problem import ProblemView


class TestInferenceErrorCategoryUnknown:
    """``UNKNOWN`` is a first-class category, not a placeholder."""

    def test_unknown_member_exists_with_string_value(self) -> None:
        assert InferenceErrorCategory.UNKNOWN
        assert str(InferenceErrorCategory.UNKNOWN) == "unknown"

    def test_unknown_is_not_retryable(self) -> None:
        assert InferenceErrorCategory.UNKNOWN.is_retryable is False

    def test_unknown_rides_the_chain_and_its_problem_invites_no_retry(self) -> None:
        err = CogtError("boom", error_category=InferenceErrorCategory.UNKNOWN)

        problem = err.to_problem(view=ProblemView.CALLER)

        assert find_inference_error_category_in_chain(err) == InferenceErrorCategory.UNKNOWN
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.is_retryable is False
