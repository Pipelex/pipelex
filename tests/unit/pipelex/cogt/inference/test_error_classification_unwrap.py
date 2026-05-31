"""Tests for ``extract_underlying_sdk_exception``.

Verifies the helper recovers the SDK exception that ``InstructorRetryException``
wraps, falling back through ``__cause__.last_attempt._exception`` when
``failed_attempts`` is empty (the tenacity-only path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tenacity import RetryError

from pipelex.cogt.inference.error_classification import extract_underlying_sdk_exception
from tests.helpers.instructor_test_utils import wrap_in_instructor_retry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestExtractUnderlyingSdkException:
    """``extract_underlying_sdk_exception`` recovers the wrapped SDK exception."""

    def test_returns_sdk_exception_from_failed_attempts(self) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc)

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is sdk_exc

    def test_falls_back_to_cause_last_attempt(self, mocker: MockerFixture) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc, include_failed_attempts=False)
        wrapped.__cause__ = RetryError(last_attempt=mocker.MagicMock(_exception=sdk_exc))

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is sdk_exc

    def test_returns_none_when_both_paths_empty(self) -> None:
        wrapped = wrap_in_instructor_retry(RuntimeError("boom"), include_failed_attempts=False)

        recovered = extract_underlying_sdk_exception(instructor_exc=wrapped)

        assert recovered is None

    def test_does_not_raise_on_malformed_input(self) -> None:
        class _Garbage:
            __cause__ = "not an exception"
            failed_attempts = "not iterable in the documented way"

        recovered = extract_underlying_sdk_exception(instructor_exc=_Garbage())

        assert recovered is None
