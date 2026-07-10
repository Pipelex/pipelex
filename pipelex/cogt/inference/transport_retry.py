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
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential

# Transient HTTP statuses worth retrying in the default (ambiguous-failure-tolerant) mode — the
# same floor the provider SDKs apply. Connection-level failures (no HTTP response at all) are
# handled separately by the exception-type check.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})
# The subset of transient statuses still safe to retry for a non-idempotent submit-style POST,
# because the server proved it did no billable work: 408 — the request body never fully arrived;
# 429 — the request was rejected at the rate-limit gate before any processing. Every other
# transient status is withheld in that mode: an ambiguous 5xx may have been processed before the
# server failed, and a 409 means the server processed the request far enough to detect a conflict.
_SUBMIT_SAFE_STATUS_CODES: frozenset[int] = frozenset({408, 429})
# Transport failures still safe to retry for a non-idempotent submit-style POST: the connection
# was never established (ConnectError / ConnectTimeout) or never acquired from the pool
# (PoolTimeout), so the request was never delivered. A ReadTimeout / WriteTimeout / ReadError can
# fire after the request reached the server, so the broader TransportError family is withheld.
_PRE_REQUEST_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)
# The OpenAI / Anthropic SDKs honor Retry-After only up to ~60s, then fall back to backoff; match
# that boundary — a longer wait is the durable-execution track's job, not something to chase in direct mode.
_MAX_RETRY_AFTER_SECONDS: float = 60.0

# Full-jitter exponential backoff: each wait is drawn from uniform(0, exponential_bound) so
# retries that were rate-limited together do not re-fire in lockstep as a thundering herd.
_exponential_wait = wait_random_exponential(multiplier=1.0, max=_MAX_RETRY_AFTER_SECONDS)


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
    if parsed_date.tzinfo is None:
        # A zoneless or "-0000" HTTP-date parses to a naive datetime; subtracting it from an
        # aware "now" would raise TypeError. Treat such a malformed header as unusable.
        return None
    return max((parsed_date - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _transport_retry_wait(retry_state: RetryCallState) -> float:
    """Honor a ``Retry-After`` header when the failure carried one, else full-jitter exponential backoff."""
    outcome = retry_state.outcome
    if outcome is not None and outcome.failed:
        exc = outcome.exception()
        if isinstance(exc, httpx.HTTPStatusError):
            retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
            if retry_after is not None:
                return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
    return _exponential_wait(retry_state)


def _make_retry_predicate(*, retry_on_ambiguous_failure: bool) -> Callable[[BaseException], bool]:
    """Build the retry predicate for the configured idempotency posture.

    With ``retry_on_ambiguous_failure`` True the predicate retries the full transient set — every
    transient HTTP status and the whole ``TransportError`` family — matching the provider SDKs'
    retry floor. With it False (a non-idempotent submit-style POST), it retries only failures that
    prove the server did no billable work: the request was never delivered, or the server rejected
    it before acting on it.
    """

    def should_retry(exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            if status_code not in _TRANSIENT_STATUS_CODES:
                return False
            # A submit-style POST must not be retried once the request reached the server: an
            # ambiguous 5xx may have been processed before it failed, and a 409 means a conflict
            # was already detected. Only 408 / 429 prove the server rejected it before any work.
            return retry_on_ambiguous_failure or status_code in _SUBMIT_SAFE_STATUS_CODES
        if retry_on_ambiguous_failure:
            # TransportError covers connection errors and timeouts — the request did not complete.
            return isinstance(exc, httpx.TransportError)
        # A submit-style POST may only be retried on a transport failure that proves the request
        # was never delivered: a ReadTimeout can fire after the server received and started it.
        return isinstance(exc, _PRE_REQUEST_TRANSPORT_ERRORS)

    return should_retry


async def request_with_transport_retry(
    send_request: Callable[[], Awaitable[httpx.Response]],
    *,
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
        retry=retry_if_exception(_make_retry_predicate(retry_on_ambiguous_failure=retry_on_ambiguous_failure)),
        wait=_transport_retry_wait,
        stop=stop_after_attempt(max_retries + 1),
        reraise=True,
    )
    return await retrying(send_request)
