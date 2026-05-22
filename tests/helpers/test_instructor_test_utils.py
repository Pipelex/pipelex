"""Sanity tests for the shared instructor test helpers.

These exercise the helper module itself so per-provider tests can rely on
``wrap_in_instructor_retry`` and ``DummySchema`` without retesting them.
"""

from __future__ import annotations

from instructor.core import InstructorRetryException
from pydantic import BaseModel

from tests.helpers.instructor_test_utils import DummySchema, wrap_in_instructor_retry


class TestInstructorTestUtils:
    """Verify the shared helpers behave as documented."""

    def test_wrap_with_failed_attempts_exposes_sdk_exception(self) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc)

        assert isinstance(wrapped, InstructorRetryException)
        assert wrapped.failed_attempts is not None
        assert wrapped.failed_attempts[-1].exception is sdk_exc

    def test_wrap_without_failed_attempts_leaves_attempts_empty(self) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc, include_failed_attempts=False)

        assert isinstance(wrapped, InstructorRetryException)
        assert wrapped.failed_attempts is None or wrapped.failed_attempts == []

    def test_dummy_schema_has_single_text_field(self) -> None:
        assert issubclass(DummySchema, BaseModel)
        fields = DummySchema.model_fields
        assert set(fields.keys()) == {"text"}
        assert fields["text"].annotation is str
