"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, detect content policy violations, and
recover the underlying SDK exception that ``InstructorRetryException``
wraps when ``instructor`` exhausts its retry loop.
"""

from typing import Any

_OPENAI_QUOTA_PATTERNS: tuple[str, ...] = (
    "insufficient_quota",
    "exceeded your current quota",
)

_ANTHROPIC_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota exceeded",
    "quota has been",
    "credit balance",
    "out of credits",
    "insufficient credit",
    "billing limit",
    "billing issue",
)

_CONTENT_POLICY_PATTERNS: tuple[str, ...] = (
    "content_policy",
    "content_filter",
    "safety system",
    "safety filter",
    "blocked by safety",
)

_GOOGLE_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota exceeded",
    "resource has been exhausted",
    "billing limit",
    "billing quota",
    "billing exceeded",
    "billing account",
)

_MISTRAL_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing limit",
    "billing quota",
    "out of credits",
    "insufficient credits",
)

_AWS_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "limit exceeded",
    "service quota",
)

_GATEWAY_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing limit",
    "billing quota",
    "insufficient_quota",
    "insufficient credit",
    "insufficient funds",
    "insufficient balance",
    "credits exhausted",
)


def is_quota_exhaustion_openai(error_message: str) -> bool:
    """Check if an OpenAI error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _OPENAI_QUOTA_PATTERNS)


def is_quota_exhaustion_anthropic(error_message: str) -> bool:
    """Check if an Anthropic error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _ANTHROPIC_QUOTA_PATTERNS)


def is_quota_exhaustion_google(error_message: str) -> bool:
    """Check if a Google error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _GOOGLE_QUOTA_PATTERNS)


def is_quota_exhaustion_mistral(error_message: str, status_code: int) -> bool:
    """Check if a Mistral error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _MISTRAL_QUOTA_PATTERNS)


def is_quota_exhaustion_aws(error_message: str) -> bool:
    """Check if an AWS error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _AWS_QUOTA_PATTERNS)


def is_quota_exhaustion_gateway(error_message: str, status_code: int) -> bool:
    """Check if a Portkey/Gateway error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _GATEWAY_QUOTA_PATTERNS)


def is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)


def extract_underlying_sdk_exception(instructor_exc: Any) -> BaseException | None:
    """Recover the SDK exception that caused an ``InstructorRetryException``.

    instructor's retry loop wraps the last failed attempt's exception inside
    ``InstructorRetryException``. We prefer ``failed_attempts[-1].exception``
    (the documented public attribute) and fall back to walking ``__cause__``
    (a tenacity ``RetryError`` whose ``last_attempt._exception`` holds the
    original exception) when ``failed_attempts`` is unset.

    Args:
        instructor_exc: The ``InstructorRetryException`` to unwrap. Typed as
            ``Any`` so callers don't need to import ``InstructorRetryException``
            just for the call site, and so malformed inputs are tolerated.

    Returns:
        The underlying SDK exception when one can be recovered, ``None`` when
        neither path yields a ``BaseException``.
    """
    failed_attempts: Any = getattr(instructor_exc, "failed_attempts", None)
    if failed_attempts:
        try:
            last_attempt = failed_attempts[-1]
        except (TypeError, KeyError, IndexError):
            last_attempt = None
        if last_attempt is not None:
            last_exc = getattr(last_attempt, "exception", None)
            if isinstance(last_exc, BaseException):
                return last_exc
    cause: Any = getattr(instructor_exc, "__cause__", None)
    last_attempt = getattr(cause, "last_attempt", None)
    if last_attempt is not None:
        underlying = getattr(last_attempt, "_exception", None)
        if isinstance(underlying, BaseException):
            return underlying
    return None
