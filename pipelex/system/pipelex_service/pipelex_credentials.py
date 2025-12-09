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


class PipelexCredentials:
    """Hardcoded credentials for Pipelex's internal services."""

    # PostHog host for Pipelex services
    POSTHOG_HOST = "https://eu.i.posthog.com"

    # Pipelex PostHog project API key (write-only, safe to embed)
    # This is used for event capture only
    POSTHOG_PROJECT_API_KEY = "phc_HPJnNKpIXh0SxNDYyTAyUtnq9KxNNZJWQszynsWVx4Y"

    # Public URL for remote gateway configuration (JSON file on S3)
    REMOTE_CONFIG_URL = "https://pipelex-config-1.s3.amazonaws.com/pipelex_remote_config.json"


# Privacy flags for Pipelex telemetry
# These ensure we don't capture sensitive user data
PIPELEX_TELEMETRY_CAPTURE_CONTENT_ENABLED = False
PIPELEX_TELEMETRY_CAPTURE_PIPE_CODES_ENABLED = False
PIPELEX_TELEMETRY_CAPTURE_OUTPUT_CLASS_NAME_ENABLED = False
