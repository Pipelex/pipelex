"""Remote configuration provider for Pipelex Gateway.

Fetches gateway configuration from a public S3 URL.
"""

import httpx
from pydantic import BaseModel, Field, ValidationError

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs
from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_credentials import PipelexServiceConfig
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class RemoteConfig(BaseModel):
    backend_model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")


def fetch_remote_config() -> RemoteConfig:
    """Fetch Pipelex Service remote configuration.

    Returns:
        RemoteConfig.

    Raises:
        RemoteConfigFetchError: If the HTTP request fails or returns an error.
        RemoteConfigValidationError: If the JSON doesn't match expected schema.
    """
    url = PipelexServiceConfig.REMOTE_CONFIG_URL

    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        msg = f"Timeout while fetching remote configuration from {url}: {exc}"
        raise RemoteConfigFetchError(msg) from exc
    except httpx.HTTPStatusError as exc:
        msg = f"HTTP error {exc.response.status_code} while fetching remote configuration from {url}"
        raise RemoteConfigFetchError(msg) from exc
    except httpx.RequestError as exc:
        msg = f"Failed to fetch remote configuration from {url}: {exc}"
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
