"""Embedded Pipelex credentials for internal services.

These credentials are used for:
1. Fetching remote configuration
2. Mandatory telemetry when using Pipelex Gateway

The PostHog project API key is write-only and used for event capture.
"""

import hashlib

# Environment variable name for Pipelex Gateway API key
PIPELEX_GATEWAY_API_KEY_VAR = "PIPELEX_GATEWAY_API_KEY"


def hash_gateway_api_key(api_key: str) -> str:
    """Hash the gateway API key using SHA256 for use as PostHog distinct_id.

    Args:
        api_key: The raw Pipelex Gateway API key.

    Returns:
        SHA256 hex digest of the API key.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class PipelexServiceConfig:
    """Hardcoded configuration for Pipelex's services."""

    # PostHog host for Pipelex services
    POSTHOG_HOST = "https://eu.i.posthog.com"

    # Pipelex PostHog project API key (write-only, safe to embed)
    # This is used for event capture only
    POSTHOG_PROJECT_API_KEY = "phc_HPJnNKpIXh0SxNDYyTAyUtnq9KxNNZJWQszynsWVx4Y"

    # Public URL for remote gateway configuration (JSON file on S3)
    REMOTE_CONFIG_URL = "https://pipelex-config.s3.amazonaws.com/pipelex_remote_config.json"
