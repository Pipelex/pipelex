"""Exceptions for Pipelex managed services."""

from pipelex.system.exceptions import PipelexError


class PipelexServiceConfigValidationError(PipelexError):
    """Raised when pipelex_service.toml validation fails."""


class PipelexServiceError(PipelexError):
    """Base exception for Pipelex service errors."""


class RemoteConfigFetchError(PipelexServiceError):
    """Raised when fetching remote configuration from PostHog fails.

    This error occurs when:
    - Network request to PostHog fails
    - Feature flag is not found or disabled
    - Payload is missing or malformed
    """


class RemoteConfigValidationError(PipelexServiceError):
    """Raised when remote configuration payload validation fails.

    This error occurs when:
    - JSON payload is not valid
    - Required keys are missing
    - Payload structure doesn't match expected schema
    """


class GatewayTermsNotAcceptedError(PipelexServiceError):
    """Raised when Pipelex Gateway is enabled but terms are not accepted.

    Users must accept the Pipelex Gateway terms of service before using
    the gateway backend. This can be done via `pipelex init config` command.
    """

    def __init__(self) -> None:
        msg = (
            "Pipelex Gateway is enabled but terms have not been accepted.\n"
            "To use Pipelex Gateway, you must accept our terms of service.\n"
            "Run `pipelex init config` to configure your backends and accept the terms.\n"
            "Alternatively, disable pipelex_gateway in .pipelex/inference/backends.toml\n"
            "and use your own API keys with direct provider backends.\n"
            "For more information: https://docs.pipelex.com/gateway\n"
            "Questions? Join our Discord: https://go.pipelex.com/discord"
        )
        super().__init__(msg)


class GatewayApiKeyMissingError(PipelexServiceError):
    """Raised when Pipelex Gateway is enabled but the API key is not set.

    Users must set the PIPELEX_GATEWAY_API_KEY environment variable to use
    the gateway backend.
    """

    def __init__(self) -> None:
        msg = (
            "Pipelex Gateway is enabled but PIPELEX_GATEWAY_API_KEY is not set.\n"
            "Please set the PIPELEX_GATEWAY_API_KEY environment variable.\n"
            "You can get a key at: https://pipelex.com/gateway\n"
            "Alternatively, disable pipelex_gateway in .pipelex/inference/backends.toml\n"
            "and use your own API keys with direct provider backends.\n"
            "For more information: https://docs.pipelex.com/gateway\n"
            "Questions? Join our Discord: https://go.pipelex.com/discord"
        )
        super().__init__(msg)


class GatewayTelemetryManagerInjectedError(PipelexServiceError):
    """Raised when a custom TelemetryManager is injected while using Pipelex Gateway.

    Pipelex Gateway requires its own telemetry setup for service monitoring.
    Dependency-injecting a TelemetryManager is not allowed when gateway is enabled.
    """

    def __init__(self) -> None:
        msg = (
            "Cannot inject a custom TelemetryManager when Pipelex Gateway is enabled.\n"
            "Gateway requires its own telemetry setup for service monitoring.\n\n"
            "You can still add your own telemetry via .pipelex/telemetry.toml:\n"
            "  - PostHog: set host and project_api_key\n"
            "  - Langfuse: set langfuse_enabled = true (requires env vars)\n"
            "  - Any OTLP backend: set otlp_endpoint and otlp_headers\n\n"
            "These will work alongside Gateway telemetry.\n"
            "Remove the telemetry_manager parameter from Pipelex.make() to proceed."
        )
        super().__init__(msg)


class GatewayDoNotTrackConflictError(PipelexServiceError):
    """Raised when DO_NOT_TRACK is set but Pipelex Gateway requires telemetry.

    Pipelex Gateway requires telemetry for service monitoring, but this conflicts
    with the user's explicit request to not be tracked.
    """

    def __init__(self, dnt_env_var: str) -> None:
        msg = (
            f"Pipelex Gateway requires telemetry, but '{dnt_env_var}' is set.\n"
            "We respect your Do Not Track preference.\n\n"
            "To use Pipelex Gateway, unset the DO_NOT_TRACK environment variable.\n"
            "Alternatively, disable pipelex_gateway in .pipelex/inference/backends.toml\n"
            "and use your own API keys with direct provider backends.\n\n"
            "For more information: https://docs.pipelex.com/gateway\n"
            "Questions? Join our Discord: https://go.pipelex.com/discord"
        )
        super().__init__(msg)


class GatewayOverrideWarning(UserWarning):
    """Warning issued when local gateway overrides are applied."""


class GatewayConfigMergeError(PipelexServiceError):
    """Raised when gateway configuration merge encounters invalid data.

    This error occurs when:
    - Local override for a model is not a dictionary
    - Remote config for a model is not a dictionary
    """
