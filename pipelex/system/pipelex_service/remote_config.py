import httpx
from pydantic import BaseModel, Field, ValidationError
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipelex import log
from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs
from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

# Retry configuration for remote config fetch
# Using hardcoded values since this runs before config is fully loaded
_FETCH_MAX_RETRIES = 5
_FETCH_WAIT_MULTIPLIER = 1
_FETCH_WAIT_MIN = 1
_FETCH_WAIT_MAX = 10
_FETCH_TIMEOUT = 10.0


class RemoteConfig(BaseModel):
    backend_model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempts for remote config fetch."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.verbose(f"Remote config fetch attempt {retry_state.attempt_number} failed: {exc}. Retrying...")


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.RequestError)),
    stop=stop_after_attempt(_FETCH_MAX_RETRIES),
    wait=wait_exponential(multiplier=_FETCH_WAIT_MULTIPLIER, min=_FETCH_WAIT_MIN, max=_FETCH_WAIT_MAX),
    before_sleep=_log_retry_attempt,
    reraise=True,
)
def _fetch_remote_config_with_retry(url: str) -> httpx.Response:
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
    response = httpx.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response


def fetch_remote_config() -> RemoteConfig:
    """Fetch Pipelex Service remote configuration.

    Returns:
        RemoteConfig.

    Raises:
        RemoteConfigFetchError: If the HTTP request fails or returns an error.
        RemoteConfigValidationError: If the JSON doesn't match expected schema.
    """
    url = PipelexDetails.REMOTE_CONFIG_URL

    try:
        response = _fetch_remote_config_with_retry(url)
    except httpx.TimeoutException as exc:
        msg = f"Timeout while fetching remote configuration from {url}: {exc}"
        raise RemoteConfigFetchError(msg) from exc
    except httpx.HTTPStatusError as exc:
        msg = f"HTTP error {exc.response.status_code} while fetching remote configuration from {url}"
        raise RemoteConfigFetchError(msg) from exc
    except httpx.RequestError as exc:
        msg = f"Failed to fetch remote configuration from {url} after {_FETCH_MAX_RETRIES} attempts: {exc}"
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
