"""Remote configuration provider for Pipelex Gateway.

Fetches gateway configuration from a public S3 URL.
"""

from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_credentials import PipelexCredentials
from pipelex.tools.log.log import log
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class GatewayRemoteConfig(BaseModel):
    """Structure of the remote configuration JSON.

    The JSON contains:
    - backend: model specs in the standard backend format
    """

    backend: dict[str, Any] = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")


def fetch_gateway_remote_config() -> GatewayRemoteConfig:
    """Fetch gateway configuration.

    Returns:
        GatewayRemoteConfig containing the backend model specifications.

    Raises:
        RemoteConfigFetchError: If the HTTP request fails or returns an error.
        RemoteConfigValidationError: If the JSON doesn't match expected schema.
    """
    url = PipelexCredentials.REMOTE_CONFIG_URL

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

    log.verbose(config_dict, title="Received remote config from S3")

    # Validate the structure
    try:
        config = GatewayRemoteConfig.model_validate(config_dict)
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Remote configuration validation failed: {validation_error_msg}"
        raise RemoteConfigValidationError(msg) from exc

    return config
