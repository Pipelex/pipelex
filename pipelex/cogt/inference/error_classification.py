"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, detect content policy violations, and
recover the underlying SDK exception that ``InstructorRetryException``
wraps when ``instructor`` exhausts its retry loop.
"""

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TypeAlias, cast

import httpx
from pydantic import BaseModel, Field

from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.types import StrEnum

# SDK exception class-name substrings that identify a network/transport failure
# (no HTTP status reached us). Matched case-insensitively against
# ``sdk_exception_type`` — covers httpx transport errors, SDK timeout/connection
# errors, Mistral's ``NoResponseError``, and builtin ``TimeoutError``.
_NETWORK_ERROR_TOKENS: tuple[str, ...] = ("timeout", "connect", "transport", "noresponse")


def _resolve_sdk_exception_type(exc: BaseException, status_code: int | None) -> str:
    """Return the ``sdk_exception_type`` name, normalizing status-less httpx transport errors.

    Some ``httpx.TransportError`` subclasses (``ReadError``, ``WriteError``,
    ``CloseError``, ``RemoteProtocolError``, ``ProxyError``, ``UnsupportedProtocol``,
    ``NetworkError``) have names that contain none of the recognized
    ``_NETWORK_ERROR_TOKENS``, so without normalization the classifier would treat
    them as ``UNKNOWN`` instead of transient transport failures. We surface them
    as ``"TransportError"`` only when the original name lacks a recognized token —
    ``ConnectError`` / ``ReadTimeout`` / ``ConnectTimeout`` etc. already match
    and stay unchanged so their semantic stays in the metadata.
    """
    raw = type(exc).__name__
    if status_code is None and isinstance(exc, httpx.TransportError):
        if not any(token in raw.lower() for token in _NETWORK_ERROR_TOKENS):
            return "TransportError"
    return raw


class ProviderErrorMetadata(BaseModel):
    """Structured SDK metadata attached to inference errors.

    Carries information downstream consumers (retry, temporal, CLI) need
    without having to scrape it back from the exception chain.
    """

    provider: ProviderName
    sdk_exception_type: str
    # Human-readable error text from the SDK exception (``str(exc)``). Both the
    # Classify step (quota / content-policy discrimination) and the Render step
    # (message composition) read it, so the Extract step must capture it.
    message: str = ""
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    # Raw provider response body — can carry account ids, billing details, or
    # credential fragments, so it is excluded from serialization (CLI JSON,
    # agent output, Temporal error details) while staying available in-process.
    body: Any | None = Field(default=None, exclude=True)

    @property
    def is_quota_exhaustion(self) -> bool:
        """Whether this error is a quota/credits exhaustion rather than rate limiting.

        Dispatches on ``provider`` because each provider phrases quota
        exhaustion differently; Mistral and Gateway also use HTTP 402.
        """
        match self.provider:
            case ProviderName.OPENAI:
                return _is_quota_exhaustion_openai(self.message)
            case ProviderName.ANTHROPIC:
                return _is_quota_exhaustion_anthropic(self.message)
            case ProviderName.GOOGLE:
                return _is_quota_exhaustion_google(self.message)
            case ProviderName.MISTRAL:
                return _is_quota_exhaustion_mistral(self.message, self.status_code or 0)
            case ProviderName.BEDROCK:
                return _is_quota_exhaustion_aws(self.message, self.provider_error_code)
            case ProviderName.GATEWAY:
                return _is_quota_exhaustion_gateway(self.message, self.status_code or 0)
            case (
                ProviderName.AZURE | ProviderName.FAL | ProviderName.HUGGINGFACE | ProviderName.LINKUP | ProviderName.DOCLING | ProviderName.PYPDFIUM2
            ):
                return False

    @property
    def is_content_policy_violation(self) -> bool:
        """Whether the error indicates a content policy / safety filter violation.

        Checks the structured ``provider_error_code`` (e.g. FAL surfaces
        ``ContentPolicyViolation`` here without echoing it into the message),
        the rendered ``message``, and the in-process ``body`` payload. ``body``
        is scanned because Azure REST returns the safety phrasing only in the
        response body — never in the ``HTTPStatusError`` message — and ``body``
        is ``exclude=True`` on serialization so the scan stays in-process.
        """
        if self.provider_error_code and "contentpolicy" in self.provider_error_code.lower():
            return True
        if _is_content_policy_violation(self.message):
            return True
        return self.body is not None and _is_content_policy_violation(_stringify_for_scan(self.body))

    @property
    def is_network_error(self) -> bool:
        """Whether this is a network/transport failure that never reached an HTTP status."""
        if self.status_code is not None:
            return False
        lowered = self.sdk_exception_type.lower()
        return any(token in lowered for token in _NETWORK_ERROR_TOKENS)


# Readable alias for the Classify / Render pipeline: the metadata model is the
# structured envelope those steps consume.
SDKErrorEnvelope: TypeAlias = ProviderErrorMetadata


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


def _is_quota_exhaustion_openai(error_message: str) -> bool:
    """Check if an OpenAI error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _OPENAI_QUOTA_PATTERNS)


def _is_quota_exhaustion_anthropic(error_message: str) -> bool:
    """Check if an Anthropic error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _ANTHROPIC_QUOTA_PATTERNS)


def _is_quota_exhaustion_google(error_message: str) -> bool:
    """Check if a Google error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _GOOGLE_QUOTA_PATTERNS)


def _is_quota_exhaustion_mistral(error_message: str, status_code: int) -> bool:
    """Check if a Mistral error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _MISTRAL_QUOTA_PATTERNS)


def _is_quota_exhaustion_aws(error_message: str, provider_error_code: str | None) -> bool:
    """Check if an AWS error indicates quota/credits exhaustion rather than rate limiting.

    AWS botocore puts the canonical signal in the error ``Code`` (e.g.
    ``ServiceQuotaExceededException``), which ``extract_bedrock_metadata`` surfaces
    as ``provider_error_code``. Some payloads also echo the situation in the
    ``Message`` text — we check both so a quota exception with a vague message is
    still detected.
    """
    if provider_error_code == "ServiceQuotaExceededException":
        return True
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _AWS_QUOTA_PATTERNS)


def _is_quota_exhaustion_gateway(error_message: str, status_code: int) -> bool:
    """Check if a Portkey/Gateway error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _GATEWAY_QUOTA_PATTERNS)


def _is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)


def _stringify_for_scan(body: Any) -> str:
    """Render a metadata body into a lowercase string for content-policy / quota probing.

    Used only by in-process scanners that need to inspect the response payload; the
    return value is never surfaced to users (``body`` is ``exclude=True``).
    """
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, default=str)
    except (TypeError, ValueError):
        return str(body)


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
    """Parse a ``Retry-After`` header value into a delay in seconds.

    The HTTP spec allows two forms: a non-negative number of seconds, or an
    HTTP-date. Numeric values are returned directly; HTTP-date values are
    converted to a delay relative to now, clamped to ``0.0`` when already past.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if not isinstance(value, str):
        return None
    try:
        retry_date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_date.tzinfo is None:
        retry_date = retry_date.replace(tzinfo=timezone.utc)
    delta_seconds = (retry_date - datetime.now(timezone.utc)).total_seconds()
    return max(delta_seconds, 0.0)


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
        provider=ProviderName.OPENAI,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
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
        provider=ProviderName.ANTHROPIC,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
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


def _parse_response_text_body(response: Any) -> tuple[Any | None, str | None]:
    """Read ``response.text`` and recover ``(body, provider_error_code)`` on a best-effort basis.

    Used by providers that deliver the response body as a *raw string* (Azure REST,
    FAL, HuggingFace, Mistral) — JSON-parse it when possible, fall back to the raw
    string for HTML / non-JSON bodies. The provider-error-code probe tries both the
    nested ``{"error": {...}}`` shape and the flat ``{"type": ..., "code": ...}``
    shape so the same helper works across providers.

    Returns ``(None, None)`` when the response has no text. Returns
    ``(raw_string, None)`` for non-JSON bodies. Returns ``(parsed_dict, code)``
    when the body parses as a JSON dict.
    """
    if response is None:
        return None, None
    raw_text = getattr(response, "text", None)
    if not isinstance(raw_text, str) or not raw_text:
        return None, None
    try:
        parsed: Any = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return raw_text, None
    if not isinstance(parsed, dict):
        return raw_text, None
    parsed_dict = cast("dict[str, Any]", parsed)
    code = _provider_error_code_from_body(parsed_dict) or _provider_error_code_from_flat_body(parsed_dict)
    return parsed_dict, code


def _google_provider_error_code_from_details(details: Any) -> str | None:
    """Read the symbolic ``status`` (e.g. ``RESOURCE_EXHAUSTED``) from a Google error payload.

    Google API error responses typically look like
    ``{"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}}``,
    but some endpoints flatten the same field to the top level. Try the nested
    shape first, then the top-level fallback.
    """
    if not isinstance(details, dict):
        return None
    details_dict = cast("dict[str, Any]", details)
    error_section = details_dict.get("error")
    if isinstance(error_section, dict):
        error_dict = cast("dict[str, Any]", error_section)
        nested_status = error_dict.get("status")
        if isinstance(nested_status, str):
            return nested_status
    top_status = details_dict.get("status")
    if isinstance(top_status, str):
        return top_status
    return None


def extract_google_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Google GenAI SDK exception into a ``ProviderErrorMetadata``.

    Google's exception shape differs from OpenAI/Anthropic:

    - ``APIError`` (and subclasses ``ClientError`` / ``ServerError``) expose
      ``code: int`` (the HTTP status code — *not* ``status_code``), ``message``,
      ``status`` (the symbolic name like ``RESOURCE_EXHAUSTED``), and
      ``details`` (the raw response JSON dict).
    - ``response`` may be ``None`` or any of ``httpx.Response`` /
      ``requests.Response`` / ``ReplayResponse``. We read ``x-goog-request-id``
      and ``retry-after`` from ``response.headers`` when present.
    """
    code = getattr(exc, "code", None)
    status_code = code if isinstance(code, int) else None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-goog-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    details = getattr(exc, "details", None)
    return ProviderErrorMetadata(
        provider=ProviderName.GOOGLE,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code),
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=_google_provider_error_code_from_details(details),
        body=details,
    )


def extract_azure_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an Azure REST API error (``httpx`` exception) into a ``ProviderErrorMetadata``.

    Azure REST returns errors as plain ``httpx`` exceptions — there is no SDK
    exception layer like Anthropic/OpenAI. We read fields off ``exc.response``
    when available (status code, headers, body) and JSON-parse the body on a
    best-effort basis. ``httpx.ConnectError`` / ``httpx.TimeoutException`` carry
    only a request; every status-related field comes back as ``None``.
    """
    return _build_azure_metadata(
        response=getattr(exc, "response", None),
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
    )


def extract_azure_metadata_from_response(response: Any, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Distill a *successful* Azure REST response into a ``ProviderErrorMetadata``.

    Used when the HTTP status was fine but the body failed to parse (malformed
    JSON): there is no ``httpx`` exception carrying the response, so the caller
    passes the ``httpx.Response`` directly along with the failure's type name
    and message.
    """
    return _build_azure_metadata(response=response, sdk_exception_type=sdk_exception_type, message=message)


def _build_azure_metadata(response: Any, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Read status code, headers, and body off an Azure ``httpx.Response`` on a best-effort basis."""
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-ms-request-id") or headers.get("apim-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.AZURE,
        sdk_exception_type=sdk_exception_type,
        message=message,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_fal_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a FAL SDK exception into a ``ProviderErrorMetadata``.

    FAL's ``FalClientHTTPError`` carries ``status_code``, ``response_headers``
    (a plain dict), ``response`` (an httpx.Response), and ``error_type``
    (a SDK-level discriminator like ``ContentPolicyViolation``).
    ``FalClientTimeoutError`` / ``FalClientError`` / ``MissingCredentialsError``
    have no response metadata; every status field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response_headers = getattr(exc, "response_headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if response_headers is not None:
        request_id_value = response_headers.get("x-request-id") or response_headers.get("x-fal-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(response_headers.get("retry-after"))
    error_type = getattr(exc, "error_type", None)
    base_provider_error_code: str | None = error_type if isinstance(error_type, str) else None
    response = getattr(exc, "response", None)
    body, parsed_provider_error_code = _parse_response_text_body(response)
    # Prefer the SDK's ``error_type`` attribute (FAL's canonical signal) over a
    # code recovered from the body.
    provider_error_code = base_provider_error_code or parsed_provider_error_code
    return ProviderErrorMetadata(
        provider=ProviderName.FAL,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_huggingface_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a HuggingFace ``HfHubHTTPError`` / ``InferenceTimeoutError`` into a ``ProviderErrorMetadata``.

    HuggingFace wraps a ``requests.Response`` (not ``httpx.Response``); the
    ``request_id`` is mirrored onto ``exc.request_id`` by ``HfHubHTTPError.__init__``
    (sourced from headers like ``X-Request-Id`` / ``X-Amzn-Trace-Id`` / ``X-Amz-Cf-Id``).
    Network-level failures (``InferenceTimeoutError``, raw ``requests`` exceptions)
    carry no response metadata; every status field comes back as ``None``.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.HUGGINGFACE,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_gateway_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Portkey/Gateway SDK exception into a ``ProviderErrorMetadata``.

    ``APIStatusError`` subclasses expose ``status_code``, ``response`` (httpx),
    and ``body`` (already a pre-parsed dict — Portkey mirrors the OpenAI SDK
    style here). ``APIConnectionError`` / ``APITimeoutError`` carry only a
    request; every status field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id") or headers.get("x-portkey-trace-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body: Any = getattr(exc, "body", None)
    provider_error_code = _provider_error_code_from_body(body) or _provider_error_code_from_flat_body(body)
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


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
        provider=ProviderName.MISTRAL,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code),
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


# AWS Bedrock surfaces its canonical error signal as a code string; a
# hand-built ``ClientError`` (and some botocore paths) may carry no HTTP status.
# This maps the documented Bedrock error codes to an HTTP status so the
# provider-blind Classify step can treat Bedrock uniformly. Used only as a
# fallback when ``ResponseMetadata.HTTPStatusCode`` is absent.
_AWS_ERROR_CODE_TO_STATUS: dict[str, int] = {
    "ThrottlingException": 429,
    "ServiceQuotaExceededException": 400,
    "AccessDeniedException": 403,
    "UnauthorizedException": 401,
    "ValidationException": 400,
    "ModelNotReadyException": 429,
    "ServiceUnavailableException": 503,
    "InternalServerException": 500,
    "ResourceNotFoundException": 404,
    "ModelNotFoundException": 404,
}


def extract_bedrock_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an AWS Bedrock ``botocore.exceptions.ClientError`` into a ``ProviderErrorMetadata``.

    botocore exposes a single ``response`` dict shaped like
    ``{"Error": {"Code": ..., "Message": ...}, "ResponseMetadata":
    {"RequestId": ..., "HTTPStatusCode": ..., "HTTPHeaders": {...}}}``.
    The ``provider_error_code`` we surface is the AWS error code (e.g.
    ``ThrottlingException``); the JSON ``body`` we keep is the full
    ``response`` dict so downstream consumers can recover the original
    error message and any extra fields without scraping ``str(exc)``.
    """
    response = getattr(exc, "response", None)
    response_dict = cast("dict[str, Any]", response) if isinstance(response, dict) else None
    error_section: dict[str, Any] = {}
    response_metadata: dict[str, Any] = {}
    if response_dict is not None:
        raw_error = response_dict.get("Error")
        if isinstance(raw_error, dict):
            error_section = cast("dict[str, Any]", raw_error)
        raw_meta = response_dict.get("ResponseMetadata")
        if isinstance(raw_meta, dict):
            response_metadata = cast("dict[str, Any]", raw_meta)
    status_code_value = response_metadata.get("HTTPStatusCode")
    status_code = status_code_value if isinstance(status_code_value, int) else None
    request_id_value = response_metadata.get("RequestId")
    request_id = request_id_value if isinstance(request_id_value, str) else None
    headers = response_metadata.get("HTTPHeaders")
    retry_after_seconds: float | None = None
    if isinstance(headers, dict):
        # botocore lowercases all HTTPHeaders keys, so ``retry-after`` is the canonical lookup.
        retry_after_seconds = _parse_retry_after_seconds(cast("dict[str, Any]", headers).get("retry-after"))
    error_code = error_section.get("Code")
    provider_error_code = error_code if isinstance(error_code, str) else None
    if status_code is None and provider_error_code is not None:
        status_code = _AWS_ERROR_CODE_TO_STATUS.get(provider_error_code)
    return ProviderErrorMetadata(
        provider=ProviderName.BEDROCK,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=response_dict,
    )


def extract_linkup_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Linkup SDK exception into a ``ProviderErrorMetadata``.

    The Linkup Python SDK raises typed exceptions (``LinkupAuthenticationError``,
    ``LinkupTooManyRequestsError``, ``LinkupInvalidRequestError`` …) that wrap
    a plain message string but do not carry the underlying HTTP ``response``,
    ``status_code``, ``request_id``, or ``retry-after`` header. Every
    status-related field comes back as ``None``; the SDK class name is the
    main discriminator. We expose the exception class name as
    ``provider_error_code`` so downstream consumers can branch on it without
    importing the Linkup SDK at the call site.
    """
    return ProviderErrorMetadata(
        provider=ProviderName.LINKUP,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=type(exc).__name__,
        body=None,
    )


_LOCAL_EXTRACT_TYPE_HIERARCHY: tuple[tuple[type[BaseException], str], ...] = (
    # ``FileNotFoundError`` is itself an ``OSError`` subclass, so it must be probed
    # first; otherwise a missing file would normalize to ``OSError`` → TRANSIENT
    # instead of CONTENT.
    (FileNotFoundError, "FileNotFoundError"),
    (ValueError, "ValueError"),
    (RuntimeError, "RuntimeError"),
    (OSError, "OSError"),
)


def extract_local_extract_metadata(exc: BaseException, provider: ProviderName) -> ProviderErrorMetadata:
    """Distill a local (non-HTTP) extraction exception into a ``ProviderErrorMetadata``.

    Local extractors (``docling``, ``pypdfium2`` …) run in-process against the
    file system; there is no HTTP response, no request id, no retry-after.
    The only meaningful signal is the underlying exception class
    (``FileNotFoundError``, ``ValueError``, ``RuntimeError``, ``OSError``),
    which we expose as ``sdk_exception_type``. The classifier matches on exact
    type names, so we normalize ``sdk_exception_type`` to the recognized ancestor
    here — a ``PermissionError`` from docling becomes ``"OSError"`` and routes to
    TRANSIENT instead of falling through to UNKNOWN. The original subclass name
    is preserved in ``provider_error_code`` for traceability.
    """
    raw_type_name = type(exc).__name__
    normalized_type_name = raw_type_name
    for ancestor_cls, ancestor_name in _LOCAL_EXTRACT_TYPE_HIERARCHY:
        if isinstance(exc, ancestor_cls):
            normalized_type_name = ancestor_name
            break
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type=normalized_type_name,
        message=str(exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=raw_type_name,
        body=None,
    )
