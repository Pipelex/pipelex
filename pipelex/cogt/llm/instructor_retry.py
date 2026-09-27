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
    retried by ``instructor``. It ends the loop at once, and ``instructor`` raises an
    ``InstructorRetryException`` from it, which the worker unwraps with
    ``extract_underlying_sdk_exception`` to classify the SDK exception.

    Args:
        max_attempts: Total number of attempts for the schema re-ask loop — the caller passes
            ``llm_job.job_config.schema_reask_max_attempts``.

    Returns:
        A fresh ``AsyncRetrying`` whose retry predicate matches only validation failures.
    """
    # Mirror the exact set `instructor` itself re-asks (`_RETRYABLE_PARSE_ERRORS` in
    # `instructor.core.retry`), so a genuine schema failure is re-asked whichever type it surfaces as:
    # pydantic's, a JSON decode error, or `ResponseParsingError` for a response with no tool call or no JSON.
    # A unit test compares this tuple with instructor's, so an upgrade that changes the set fails it.
    from instructor.core import AsyncValidationError, ResponseParsingError  # ruff: ignore[import-outside-top-level]

    return AsyncRetrying(
        retry=retry_if_exception_type((ValidationError, json.JSONDecodeError, AsyncValidationError, ResponseParsingError)),
        stop=stop_after_attempt(max_attempts),
    )
