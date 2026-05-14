"""Fetch the Pipelex Gateway remote config with retry, cache, and provenance tracking.

The fetcher is the single entry point used by ``Pipelex.setup`` and the dev/doctor CLIs.
Its public method returns a :class:`RemoteConfigResult` carrying the parsed config plus the
source it came from (``FRESH`` vs ``CACHED``), so downstream code can branch its error
messaging and disable telemetry when running off stale data.

This module emits no warnings — stale-cache surfacing is the orchestration layer's job
(see ``Pipelex.setup``). Keeping the fetcher pure means test fixtures that swap in a cached
fetcher don't need to special-case warning replay.

Behaviour:

- Every successful fetch persists the raw JSON to :class:`RemoteConfigCache` (opportunistic
  refresh).
- On network or HTTP failure, the fetcher falls back to the cache if one exists and returns
  it tagged ``source=CACHED`` with a ``cached_at`` timestamp. If no usable cache exists, it
  raises :class:`RemoteConfigUnavailableError`. The inner :class:`RemoteConfigFetchError` is
  chained as ``__cause__`` so existing surfaces (doctor, agent hints) keep working. Warning
  emission is the orchestration layer's responsibility — see ``Pipelex.setup`` — so the
  fetcher itself remains a pure data-returning function.
- On JSON-validation failure (a server-side schema break — we control the server) the
  fetcher raises :class:`RemoteConfigValidationError` and does NOT silently fall back to
  cache.
- Callers that must not bake stale data into committed files (doc generators, fixture
  preprocessors) pass ``require_fresh=True``, which turns any cache fallback into an
  :class:`RemoteConfigUnavailableError` immediately.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic v2 resolves this annotation at runtime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.pipelex_service.remote_config import PipelexPosthogConfig, RemoteConfig
from pipelex.system.pipelex_service.remote_config_cache import RemoteConfigCache
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.terminal_utils import print_to_stderr
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class RemoteConfigResult(BaseModel):
    """Outcome of a fetch attempt: the parsed config plus provenance metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    config: RemoteConfig = Field(description="The parsed remote configuration")
    source: RemoteConfigSource = Field(description="Whether the config came from the network or the on-disk cache")
    cached_at: datetime | None = Field(
        default=None,
        description="UTC timestamp from the cache snapshot when ``source == CACHED``; ``None`` otherwise",
    )


class RemoteConfigFetcher:
    """Fetches Pipelex Service remote configuration with retry logic and a cache fallback."""

    # Retry configuration for remote config fetch
    # Using hardcoded values since this runs before config is fully loaded
    FETCH_MAX_RETRIES = 5
    FETCH_WAIT_MULTIPLIER = 1
    FETCH_WAIT_MIN = 1
    FETCH_WAIT_MAX = 10
    FETCH_TIMEOUT = 10.0

    @classmethod
    def _log_retry_attempt(cls, retry_state: RetryCallState) -> None:
        """Log retry attempts for remote config fetch."""
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        print_to_stderr(f"Remote config fetch attempt {retry_state.attempt_number} failed: {exc}. Retrying...")

    @classmethod
    def _fetch_remote_config_with_retry(cls, url: str) -> httpx.Response:
        """Fetch remote config with retry logic for transient network errors.

        Args:
            url: The URL to fetch the configuration from.

        Returns:
            The HTTP response.

        Raises:
            httpx.TimeoutException: If the request times out after all retries.
            httpx.RequestError: If a network error occurs after all retries.
            httpx.HTTPStatusError: If the server returns an error status (not retried).
        """

        @retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
            stop=stop_after_attempt(cls.FETCH_MAX_RETRIES),
            wait=wait_exponential(multiplier=cls.FETCH_WAIT_MULTIPLIER, min=cls.FETCH_WAIT_MIN, max=cls.FETCH_WAIT_MAX),
            before_sleep=cls._log_retry_attempt,
            reraise=True,
        )
        def _fetch_with_retry(url: str) -> httpx.Response:
            response = httpx.get(url, timeout=cls.FETCH_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            return response

        return _fetch_with_retry(url)

    @classmethod
    def make_dummy_remote_config(cls) -> RemoteConfig:
        """Create a default RemoteConfig for testing in offline environments.

        Returns:
            A minimal RemoteConfig with analytics disabled and empty model specs.
        """
        return RemoteConfig(
            posthog=PipelexPosthogConfig(
                project_api_key="",
                endpoint="https://dummy-endpoint.pipelex.com",
                is_geoip_enabled=False,
                is_debug_enabled=False,
            ),
            backend_model_specs={},
            aws_region="us-east-1",
        )

    @classmethod
    def _fetch_fresh(cls, url: str) -> dict[str, Any]:
        """Fetch and validate-parse the remote payload. Raises ``RemoteConfigFetchError`` on
        network/HTTP failure and ``RemoteConfigValidationError`` on schema breaks. Returns the
        raw JSON payload so callers can persist it to the cache verbatim.
        """
        try:
            response = cls._fetch_remote_config_with_retry(url)
        except httpx.TimeoutException as timeout_exc:
            msg = f"Timeout while fetching remote configuration from {url}: {timeout_exc}"
            raise RemoteConfigFetchError(msg) from timeout_exc
        except httpx.HTTPStatusError as http_exc:
            msg = f"HTTP error {http_exc.response.status_code} while fetching remote configuration from {url}"
            raise RemoteConfigFetchError(msg) from http_exc
        except httpx.RequestError as request_exc:
            msg = f"Failed to fetch remote configuration from {url} after {cls.FETCH_MAX_RETRIES} attempts: {request_exc}"
            raise RemoteConfigFetchError(msg) from request_exc

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as parse_exc:
            msg = f"Failed to parse remote configuration JSON: {parse_exc}"
            raise RemoteConfigValidationError(msg) from parse_exc

        try:
            RemoteConfig.model_validate(payload)
        except ValidationError as validation_error:
            formatted = format_pydantic_validation_error(validation_error)
            msg = f"Remote configuration validation failed: {formatted}"
            raise RemoteConfigValidationError(msg) from validation_error

        return payload

    @classmethod
    def _build_unavailable_error(cls, fetch_error: RemoteConfigFetchError) -> RemoteConfigUnavailableError:
        """Build the user-facing offline-mode error with a clear remediation hint.

        Returns the exception so the caller can ``raise ... from fetch_error`` itself; this
        avoids "unreachable code" gymnastics at the call site.
        """
        cache_path = RemoteConfigCache.cache_path()
        msg = (
            f"Pipelex Gateway is enabled but the remote configuration is unreachable "
            f"and no local cache is available at {cache_path}.\n"
            f"Underlying error: {fetch_error}\n"
            "Remediation:\n"
            "  - Run `pipelex init` while online to prime the cache.\n"
            "  - Or disable pipelex_gateway in .pipelex/inference/backends.toml to operate "
            "permanently offline with your own API keys (BYOK)."
        )
        return RemoteConfigUnavailableError(msg)

    @classmethod
    def fetch_remote_config(cls, require_fresh: bool = False) -> RemoteConfigResult:
        """Fetch the Pipelex Service remote configuration.

        Args:
            require_fresh: When ``True``, refuse to serve a cached fallback. Used by
                dev-CLI generators that regenerate committed reference docs/fixtures — they
                must never bake stale data into the repo. A cache miss when offline becomes
                ``RemoteConfigUnavailableError`` immediately.

        Returns:
            A :class:`RemoteConfigResult` carrying the parsed config plus its provenance.

        Raises:
            RemoteConfigUnavailableError: Network fetch failed AND no usable cache exists
                (or ``require_fresh=True`` and only a cache is available).
            RemoteConfigValidationError: The remote responded with a payload that doesn't
                match the expected schema. Never falls back to cache for this case.
        """
        if runtime_manager.is_in_codex_cloud:
            print_to_stderr("Skipping remote config fetch in Codex Cloud, using dummy config instead")
            return RemoteConfigResult(config=cls.make_dummy_remote_config(), source=RemoteConfigSource.FRESH, cached_at=None)

        url = PipelexDetails.REMOTE_CONFIG_URL

        try:
            payload = cls._fetch_fresh(url)
        except RemoteConfigFetchError as fetch_error:
            if require_fresh:
                raise cls._build_unavailable_error(fetch_error) from fetch_error
            cached = RemoteConfigCache.load()
            if cached is None:
                raise cls._build_unavailable_error(fetch_error) from fetch_error
            return RemoteConfigResult(
                config=cached.to_remote_config(),
                source=RemoteConfigSource.CACHED,
                cached_at=cached.cached_at,
            )

        # Fresh path: persist the raw payload for future offline fallback.
        RemoteConfigCache.store(payload)
        config = RemoteConfig.model_validate(payload)
        return RemoteConfigResult(config=config, source=RemoteConfigSource.FRESH, cached_at=None)
