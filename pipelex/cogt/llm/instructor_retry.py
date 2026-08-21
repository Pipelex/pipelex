import json

from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt


def make_instructor_schema_retrying(*, max_attempts: int) -> AsyncRetrying:
    """Build a ``tenacity.AsyncRetrying`` that confines ``instructor``'s retry to schema re-ask.

    Passed a bare ``int``, ``instructor``'s ``max_retries`` builds a retry loop whose default
    predicate retries *any* exception — transport / API errors included — so it re-runs the whole
    completion on transient failures, a second retry loop nested on top of the SDK client's own
    transport retry (Tier 1). ``instructor.core.retry.initialize_retrying`` accepts a pre-built
    ``AsyncRetrying`` and uses it as-is, so passing this object instead scopes the retry to genuine
    schema re-ask: a malformed / invalid LLM output is re-asked, while a transport error is *not*
    retried by ``instructor`` and propagates immediately as the raw SDK exception for the worker's
    own ``except`` clause to classify.

    Args:
        max_attempts: Total number of attempts for the schema re-ask loop — the caller passes
            ``llm_job.job_config.schema_reask_max_attempts``.

    Returns:
        A fresh ``AsyncRetrying`` whose retry predicate matches only validation failures.
    """
    # `instructor` raises its own validation-error types alongside pydantic's; mirror the exact
    # set `instructor` itself treats as re-askable (see `instructor.core.retry.retry_async`) so a
    # genuine schema failure is still re-asked regardless of which of the two it surfaces as.
    from instructor.core import AsyncValidationError  # ruff: ignore[import-outside-top-level]
    from instructor.core import ValidationError as InstructorValidationError  # ruff: ignore[import-outside-top-level]

    return AsyncRetrying(
        retry=retry_if_exception_type((ValidationError, json.JSONDecodeError, AsyncValidationError, InstructorValidationError)),
        stop=stop_after_attempt(max_attempts),
    )
