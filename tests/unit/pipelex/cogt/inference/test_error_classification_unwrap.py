"""Tests for ``extract_underlying_sdk_exception``.

instructor raises ``InstructorRetryException`` from the last exception its retry loop saw: the raw SDK
exception when a call failed in transport, or tenacity's ``RetryError`` when the re-ask budget ran out.
``failed_attempts`` holds only the attempts whose response failed to parse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from instructor.core import FailedAttempt, InstructorRetryException
from tenacity import RetryError

from pipelex.cogt.inference.error_classification import extract_underlying_sdk_exception
from tests.helpers.instructor_test_utils import wrap_in_instructor_retry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestExtractUnderlyingSdkException:
    """``extract_underlying_sdk_exception`` recovers the exception that ended instructor's retry loop."""

    def test_returns_the_sdk_exception_the_wrapper_is_chained_from(self) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc)

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is sdk_exc

    def test_prefers_the_sdk_exception_over_an_earlier_parse_failure(self) -> None:
        """A transport failure after a re-asked parse failure is what ended the loop, so it wins."""
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc, earlier_parse_failures=[ValueError("bad shape")])

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is sdk_exc

    def test_returns_the_last_attempt_of_a_spent_retry_budget(self, mocker: MockerFixture) -> None:
        last_parse_failure = ValueError("still the wrong shape")
        wrapped = self._make_wrapper(failed_attempts=[FailedAttempt(attempt_number=1, exception=ValueError("first"))])
        wrapped.__cause__ = RetryError(last_attempt=mocker.MagicMock(_exception=last_parse_failure))

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is last_parse_failure

    def test_falls_back_to_the_last_failed_attempt_without_a_cause(self) -> None:
        parse_failure = ValueError("bad shape")
        wrapped = self._make_wrapper(failed_attempts=[FailedAttempt(attempt_number=1, exception=parse_failure)])

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is parse_failure

    def test_returns_none_when_both_paths_empty(self) -> None:
        wrapped = self._make_wrapper(failed_attempts=None)

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is None

    def test_does_not_raise_on_malformed_input(self) -> None:
        class _Garbage:
            __cause__ = "not an exception"
            failed_attempts = "not iterable in the documented way"

        recovered = extract_underlying_sdk_exception(instructor_exc=_Garbage())

        assert recovered is None

    @classmethod
    def _make_wrapper(cls, *, failed_attempts: list[FailedAttempt] | None) -> InstructorRetryException:
        return InstructorRetryException(
            "wrapped",
            last_completion=None,
            n_attempts=1,
            total_usage=0,
            create_kwargs={},
            failed_attempts=failed_attempts,
        )
