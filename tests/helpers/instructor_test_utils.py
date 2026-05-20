"""Shared test helpers for instructor-using LLM workers.

These helpers let provider-specific worker tests construct realistic
``InstructorRetryException`` wrappers around real SDK exceptions without
duplicating boilerplate. They mirror what instructor's retry loop produces at
runtime so unwrap-and-dispatch logic can be exercised end-to-end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from instructor.core import FailedAttempt, InstructorRetryException
from pydantic import BaseModel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class DummySchema(BaseModel):
    """Minimal Pydantic schema used as the response_model for unit tests."""

    text: str


def wrap_in_instructor_retry(sdk_exc: Exception, *, include_failed_attempts: bool = True) -> InstructorRetryException:
    """Build an ``InstructorRetryException`` as instructor's retry loop would.

    Args:
        sdk_exc: The underlying SDK exception that should appear as the last
            failed attempt.
        include_failed_attempts: When ``True`` (default), populate
            ``failed_attempts`` with a single :class:`FailedAttempt` wrapping
            ``sdk_exc``. When ``False``, leave ``failed_attempts`` as ``None``
            so the caller can install a tenacity ``RetryError`` on
            ``__cause__`` to exercise the fallback unwrap path.

    Returns:
        An ``InstructorRetryException`` whose ``failed_attempts[-1].exception``
        is ``sdk_exc`` (when ``include_failed_attempts`` is ``True``).
    """
    failed_attempts: list[FailedAttempt] | None = [FailedAttempt(attempt_number=1, exception=sdk_exc)] if include_failed_attempts else None
    return InstructorRetryException(
        str(sdk_exc),
        last_completion=None,
        n_attempts=1,
        total_usage=0,
        create_kwargs={},
        failed_attempts=failed_attempts,
    )


def make_llm_job(mocker: MockerFixture) -> Any:
    """Return a MagicMock ``LLMJob`` skeleton suitable for ``_gen_object`` tests.

    The returned mock has ``applied_job_params=None`` and a ``job_params`` mock
    populated with the fields ``_gen_object`` actually reads. Callers may
    override individual fields as needed.
    """
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_config.schema_reask_max_attempts = 1
    job.job_report.llm_tokens_usage = None
    return job
