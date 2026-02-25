import httpx
from pydantic import ValidationError
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.pipelex_service.remote_config import PipelexPosthogConfig, RemoteConfig
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.terminal_utils import print_to_stderr
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class RemoteConfigFetcher:
    """Fetches Pipelex Service remote configuration with retry logic."""

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
        )

    @classmethod
    def fetch_remote_config(cls) -> RemoteConfig:
        """Fetch Pipelex Service remote configuration.

        Returns:
            RemoteConfig.

        Raises:
            RemoteConfigFetchError: If the HTTP request fails or returns an error.
            RemoteConfigValidationError: If the JSON doesn't match expected schema.
        """
        # In Codex Cloud, return dummy config to avoid SSL issues with MITM proxy
        if runtime_manager.is_in_codex_cloud:
            print_to_stderr("Skipping remote config fetch in Codex Cloud, using dummy config instead")
            return cls.make_dummy_remote_config()

        url = PipelexDetails.REMOTE_CONFIG_URL

        try:
            response = cls._fetch_remote_config_with_retry(url)
        except httpx.TimeoutException as exc:
            msg = f"Timeout while fetching remote configuration from {url}: {exc}"
            raise RemoteConfigFetchError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = f"HTTP error {exc.response.status_code} while fetching remote configuration from {url}"
            raise RemoteConfigFetchError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"Failed to fetch remote configuration from {url} after {cls.FETCH_MAX_RETRIES} attempts: {exc}"
            raise RemoteConfigFetchError(msg) from exc

        # Parse JSON content
        try:
            config_dict = response.json()
        except Exception as exc:
            msg = f"Failed to parse remote configuration JSON: {exc}"
            raise RemoteConfigValidationError(msg) from exc

        # Validate the structure
        try:
            config = RemoteConfig.model_validate(config_dict)
        except ValidationError as exc:
            validation_error_msg = format_pydantic_validation_error(exc)
            msg = f"Remote configuration validation failed: {validation_error_msg}"
            raise RemoteConfigValidationError(msg) from exc

        return config
