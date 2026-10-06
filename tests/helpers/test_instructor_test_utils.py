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

    def test_wrap_chains_from_the_sdk_exception(self) -> None:
        sdk_exc = RuntimeError("boom")
        wrapped = wrap_in_instructor_retry(sdk_exc)

        assert isinstance(wrapped, InstructorRetryException)
        assert wrapped.__cause__ is sdk_exc
        assert wrapped.failed_attempts == []
        assert wrapped.n_attempts == 1

    def test_wrap_records_earlier_parse_failures_only(self) -> None:
        sdk_exc = RuntimeError("boom")
        parse_failure = ValueError("bad shape")
        wrapped = wrap_in_instructor_retry(sdk_exc, earlier_parse_failures=[parse_failure])

        assert wrapped.__cause__ is sdk_exc
        assert wrapped.failed_attempts is not None
        assert [failed_attempt.exception for failed_attempt in wrapped.failed_attempts] == [parse_failure]
        assert wrapped.n_attempts == 2

    def test_dummy_schema_has_single_text_field(self) -> None:
        assert issubclass(DummySchema, BaseModel)
        fields = DummySchema.model_fields
        assert set(fields.keys()) == {"text"}
        assert fields["text"].annotation is str
