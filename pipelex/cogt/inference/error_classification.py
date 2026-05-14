"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, detect content policy violations, and
recover the underlying SDK exception that ``InstructorRetryException``
wraps when ``instructor`` exhausts its retry loop.
"""

import json
from typing import Any, cast

from pydantic import BaseModel

from pipelex.types import StrEnum


class ProviderErrorMetadata(BaseModel):
    """Structured SDK metadata attached to inference errors.

    Carries information downstream consumers (retry, temporal, CLI) need
    without having to scrape it back from the exception chain.
    """

    provider: str
    sdk_exception_type: str
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    body: Any | None = None


class UserActionKind(StrEnum):
    """Discrete categories of advice we surface to the user/agent.

    Lets the CLI render consistent guidance and agent JSON stay typed across
    providers. The free-form ``detail`` string carries provider-specific text.
    """

    WAIT_AND_RETRY = "wait_and_retry"
    CHECK_BILLING = "check_billing"
    CHECK_CREDENTIALS = "check_credentials"
    CHANGE_INPUT = "change_input"
    CHANGE_MODEL = "change_model"
    CONTACT_SUPPORT = "contact_support"
    UNKNOWN = "unknown"


class UserAction(BaseModel):
    """Structured user-facing advice attached to an inference error.

    ``kind`` discriminates the type of action, ``detail`` is the free-form
    provider-specific advice (e.g. a billing URL, a retry hint).
    """

    kind: UserActionKind
    detail: str


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


def _parse_retry_after_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _provider_error_code_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error_section = cast("dict[str, Any]", body).get("error")
    if not isinstance(error_section, dict):
        return None
    error_dict = cast("dict[str, Any]", error_section)
    code = error_dict.get("type") or error_dict.get("code")
    if isinstance(code, str):
        return code
    return None


def extract_openai_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an OpenAI SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the SDK's two exception shapes:

    - ``APIStatusError`` subclasses (``BadRequestError``, ``RateLimitError``,
      ``AuthenticationError`` …) expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``Retry-After``), and ``body``. The SDK
      pre-unwraps ``body["error"]`` so ``body["type"]`` / ``body["code"]``
      sit at the top level — and are also mirrored to ``exc.type`` /
      ``exc.code`` as instance attributes.
    - ``APIConnectionError`` / ``APITimeoutError`` carry only a ``request``;
      every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body = getattr(exc, "body", None)
    # OpenAI's _make_status_error pre-unwraps body["error"] onto exc.type / exc.code,
    # so we read those attributes directly rather than re-parsing the body.
    error_type = getattr(exc, "type", None)
    error_code = getattr(exc, "code", None)
    provider_error_code: str | None = None
    if isinstance(error_type, str):
        provider_error_code = error_type
    elif isinstance(error_code, str):
        provider_error_code = error_code
    return ProviderErrorMetadata(
        provider="openai",
        sdk_exception_type=type(exc).__name__,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_anthropic_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an Anthropic SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the two exception shapes in the Anthropic SDK:

    - ``APIStatusError`` subclasses expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``Retry-After``) and ``body``.
    - ``APIConnectionError`` / ``APITimeoutError`` expose neither
      ``status_code`` nor ``response``; every status-related field comes back
      as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body = getattr(exc, "body", None)
    return ProviderErrorMetadata(
        provider="anthropic",
        sdk_exception_type=type(exc).__name__,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=_provider_error_code_from_body(body),
        body=body,
    )


def _provider_error_code_from_flat_body(body: Any) -> str | None:
    """Read ``type``/``code`` directly off the top-level body dict.

    Mistral returns flat error payloads (``{"message": ..., "type": ..., "code": ...}``)
    on most endpoints, in addition to the nested ``{"error": {...}}`` shape covered
    by ``_provider_error_code_from_body``.
    """
    if not isinstance(body, dict):
        return None
    flat = cast("dict[str, Any]", body)
    code = flat.get("type") or flat.get("code")
    if isinstance(code, str):
        return code
    return None


def extract_mistral_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Mistral SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the two shapes the Mistral SDK raises:

    - ``MistralError`` (and subclasses like ``SDKError``) carry ``status_code``,
      ``headers`` (httpx.Headers), and ``body`` as a *raw response text string*
      — not a pre-parsed dict like OpenAI/Anthropic. We JSON-parse it on a
      best-effort basis to recover ``provider_error_code`` from either the
      top-level ``type``/``code`` or the nested ``error.type``/``error.code``.
    - ``NoResponseError`` is a separate ``Exception`` subclass with no response
      metadata; every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(exc, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    raw_body = getattr(exc, "body", None)
    body: Any = raw_body
    provider_error_code: str | None = None
    if isinstance(raw_body, str) and raw_body:
        try:
            parsed: Any = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            parsed_dict = cast("dict[str, Any]", parsed)
            body = parsed_dict
            provider_error_code = _provider_error_code_from_flat_body(parsed_dict) or _provider_error_code_from_body(parsed_dict)
    return ProviderErrorMetadata(
        provider="mistral",
        sdk_exception_type=type(exc).__name__,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )
