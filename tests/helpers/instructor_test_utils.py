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

from pipelex.cogt.llm.llm_prompt import LLMPrompt

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class DummySchema(BaseModel):
    """Minimal Pydantic schema used as the response_model for unit tests."""

    text: str


def wrap_in_instructor_retry(sdk_exc: Exception, *, earlier_parse_failures: list[Exception] | None = None) -> InstructorRetryException:
    """Build an ``InstructorRetryException`` the way instructor's retry loop raises one around an SDK exception.

    instructor raises it ``from`` the last exception its loop saw. pipelex's re-ask predicate never retries a
    transport failure, so that last exception is the raw SDK exception, and it sits on ``__cause__``.
    ``failed_attempts`` records only the attempts whose response failed to parse, so an SDK exception never
    appears there.

    Args:
        sdk_exc: The SDK exception the last attempt raised.
        earlier_parse_failures: The parse failures of the attempts before it, oldest first, which instructor
            re-asked before the SDK exception ended the loop.

    Returns:
        An ``InstructorRetryException`` chained from ``sdk_exc``.
    """
    failed_attempts = [
        FailedAttempt(attempt_number=attempt_index + 1, exception=parse_failure)
        for attempt_index, parse_failure in enumerate(earlier_parse_failures or [])
    ]
    wrapped = InstructorRetryException(
        str(sdk_exc),
        last_completion=None,
        n_attempts=len(failed_attempts) + 1,
        total_usage=0,
        create_kwargs={},
        failed_attempts=failed_attempts,
    )
    wrapped.__cause__ = sdk_exc
    return wrapped


def make_llm_job(mocker: MockerFixture) -> Any:
    """Return a MagicMock ``LLMJob`` skeleton suitable for ``_gen_object`` tests.

    The returned mock has ``applied_job_params=None`` and a ``job_params`` mock
    populated with the fields ``_gen_object`` actually reads. ``llm_prompt`` is a
    real :class:`LLMPrompt` (not a MagicMock) so its ``system_text`` / ``user_text``
    don't leak auto-attributes into provider config/message construction. Callers
    may override individual fields as needed.
    """
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.llm_prompt = LLMPrompt(
        system_text="You are a helpful test assistant.",
        user_text="Generate a structured object.",
    )
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_config.schema_reask_max_attempts = 1
    job.job_report.llm_tokens_usage = None
    return job
