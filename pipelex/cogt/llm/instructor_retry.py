import json

from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt


def make_instructor_schema_retrying(*, max_attempts: int) -> AsyncRetrying:
    """Build a ``tenacity.AsyncRetrying`` that confines ``instructor``'s retry to schema re-ask.

    ``instructor`` accepts a pre-built ``AsyncRetrying`` as ``max_retries`` and drives its loop with
    it as-is. This one re-asks only a malformed / invalid LLM output and never retries a transport
    or API error, whose retry belongs to the SDK client alone (Tier 1): such an error ends the loop
    at once, ``instructor`` raises an ``InstructorRetryException`` from it, and the worker unwraps
    it with ``extract_underlying_sdk_exception`` to classify the SDK exception.

    A bare ``int`` would leave that scope to ``instructor``'s own default predicate. Building the
    loop here keeps it a decision of this codebase, pinned by a unit test that compares the retried
    set with ``instructor``'s, rather than one an upgrade can widen silently.

    Args:
        max_attempts: Total number of attempts for the schema re-ask loop — the caller passes
            ``llm_job.job_config.schema_reask_max_attempts``.

    Returns:
        A fresh ``AsyncRetrying`` whose retry predicate matches only validation failures.
    """
    # Mirror the exact set `instructor` itself re-asks (`_RETRYABLE_PARSE_ERRORS` in
    # `instructor.v2.core.retry`), so a genuine schema failure is re-asked whichever type it surfaces as:
    # pydantic's, a JSON decode error, or `ResponseParsingError` for a response with no tool call or no JSON.
    # A unit test compares this tuple with instructor's, so an upgrade that changes the set fails it.
    from instructor.core import AsyncValidationError, ResponseParsingError  # ruff: ignore[import-outside-top-level]

    return AsyncRetrying(
        retry=retry_if_exception_type((ValidationError, json.JSONDecodeError, AsyncValidationError, ResponseParsingError)),
        stop=stop_after_attempt(max_attempts),
    )
