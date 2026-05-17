"""Tier 1 transport retry for the genuinely SDK-less inference paths.

The SDK-backed inference workers inherit transport retry from their provider SDK (configured
explicitly from ``cogt.transport_max_retries`` in each client factory). A worker that talks to a
provider over raw ``httpx`` — with no SDK in between — has no such floor. This module provides it:
a small ``tenacity``-based async wrapper that retries transient transport failures with the same
configured budget, so the retry posture is uniform across every inference worker family.

It deliberately reuses ``tenacity`` (the same library the ``instructor`` schema-re-ask helper
uses) rather than hand-rolling a retry loop, and it must only ever wrap a path that has no SDK
retry of its own — layering it on top of a retrying SDK would double-retry.
"""

import email.utils
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential

# Transient HTTP statuses worth retrying. Connection-level failures (no HTTP response at all) are
# handled separately by the exception-type check.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})
# 5xx is the ambiguous case: the server may have processed the request before failing, so a retry
# of a non-idempotent submit-style POST could duplicate the job (double billing, double output).
_SERVER_ERROR_STATUS_CODES: frozenset[int] = frozenset({500, 502, 503, 504})
# The OpenAI / Anthropic SDKs honor Retry-After only up to ~60s, then fall back to backoff; match
# that boundary — a longer wait is the Temporal line, not something to chase in direct mode.
_MAX_RETRY_AFTER_SECONDS: float = 60.0

_exponential_wait = wait_exponential(multiplier=1.0, max=_MAX_RETRY_AFTER_SECONDS)


def _parse_retry_after(raw_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value (delta-seconds or HTTP-date) into seconds, or None."""
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return float(cleaned)
    try:
        parsed_date = email.utils.parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    return max((parsed_date - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _transport_retry_wait(retry_state: RetryCallState) -> float:
    """Honor a ``Retry-After`` header when the failure carried one, else exponential backoff."""
    outcome = retry_state.outcome
    if outcome is not None and outcome.failed:
        exc = outcome.exception()
        if isinstance(exc, httpx.HTTPStatusError):
            retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
            if retry_after is not None:
                return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
    return _exponential_wait(retry_state)


def _make_retry_predicate(retry_on_ambiguous_failure: bool) -> Callable[[BaseException], bool]:
    """Build the retry predicate: connection failures always, transient statuses conditionally."""

    def should_retry(exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code not in _TRANSIENT_STATUS_CODES:
                return False
            # A submit-style POST must not be retried on an ambiguous 5xx — the request may have
            # already landed. Connection-proven failures (TransportError) and non-5xx transient
            # statuses stay retryable because they prove the request did not take effect.
            return retry_on_ambiguous_failure or status_code not in _SERVER_ERROR_STATUS_CODES
        # TransportError covers connection errors and timeouts — the request did not complete.
        return isinstance(exc, httpx.TransportError)

    return should_retry


async def request_with_transport_retry(
    send_request: Callable[[], Awaitable[httpx.Response]],
    max_retries: int,
    retry_on_ambiguous_failure: bool = True,
) -> httpx.Response:
    """Run an SDK-less ``httpx`` request under the Tier 1 transport-retry floor.

    ``send_request`` must perform one full request attempt and raise ``httpx.HTTPStatusError`` on a
    non-2xx response (call ``raise_for_status()`` inside it) so transient statuses become retryable
    exceptions. It is called afresh on every attempt — open the ``httpx.AsyncClient`` inside it.

    Args:
        send_request: A zero-arg coroutine performing one request attempt.
        max_retries: The configured transport-retry budget (``cogt.transport_max_retries``). The
            total number of attempts is ``max_retries + 1`` — consistent with the SDK clients,
            where ``max_retries`` counts retries beyond the initial attempt.
        retry_on_ambiguous_failure: When False, an ambiguous 5xx is not retried — use this for
            non-idempotent submit-style POSTs where a retry could duplicate the work.

    Returns:
        The successful ``httpx.Response``.

    Raises:
        httpx.HTTPError: The last attempt's error, re-raised once the retry budget is exhausted.
    """
    retrying = AsyncRetrying(
        retry=retry_if_exception(_make_retry_predicate(retry_on_ambiguous_failure)),
        wait=_transport_retry_wait,
        stop=stop_after_attempt(max_retries + 1),
        reraise=True,
    )
    return await retrying(send_request)
