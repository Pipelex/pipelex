"""Pipelex managed services module.

This module contains components for Pipelex Gateway and related services:
- PipelexServiceConfig: Configuration for Pipelex services
- fetch_gateway_remote_config: Fetches remote configuration from S3
- GatewayConfigMerger: Merges remote config with local overrides
"""

# TODO: RC - empty this file
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayConfigMergeError,
    GatewayDoNotTrackConflictError,
    GatewayOverrideWarning,
    GatewayTelemetryManagerInjectedError,
    GatewayTermsNotAcceptedError,
    PipelexServiceError,
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.gateway_config_merger import GatewayConfigMerger
from pipelex.system.pipelex_service.pipelex_credentials import (
    PIPELEX_GATEWAY_API_KEY_VAR,
    PIPELEX_TELEMETRY_CAPTURE_CONTENT_ENABLED,
    PIPELEX_TELEMETRY_CAPTURE_OUTPUT_CLASS_NAME_ENABLED,
    PIPELEX_TELEMETRY_CAPTURE_PIPE_CODES_ENABLED,
    PipelexCredentials,
    hash_gateway_api_key,
)
from pipelex.system.pipelex_service.pipelex_service_config import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    GatewayConfig,
    PipelexServiceConfig,
    PipelexServiceConfigValidationError,
    load_pipelex_service_config,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.remote_config_provider import (
    GatewayRemoteConfig,
    fetch_gateway_remote_config,
)

__all__ = [
    "PIPELEX_GATEWAY_API_KEY_VAR",
    "PIPELEX_SERVICE_CONFIG_FILE_NAME",
    "PIPELEX_TELEMETRY_CAPTURE_CONTENT_ENABLED",
    "PIPELEX_TELEMETRY_CAPTURE_OUTPUT_CLASS_NAME_ENABLED",
    "PIPELEX_TELEMETRY_CAPTURE_PIPE_CODES_ENABLED",
    "GatewayApiKeyMissingError",
    "GatewayConfig",
    "GatewayConfigMergeError",
    "GatewayConfigMerger",
    "GatewayDoNotTrackConflictError",
    "GatewayOverrideWarning",
    "GatewayRemoteConfig",
    "GatewayTelemetryManagerInjectedError",
    "GatewayTermsNotAcceptedError",
    "PipelexCredentials",
    "PipelexServiceConfig",
    "hash_gateway_api_key",
    "PipelexServiceConfigValidationError",
    "PipelexServiceError",
    "RemoteConfigFetchError",
    "RemoteConfigValidationError",
    "fetch_gateway_remote_config",
    "load_pipelex_service_config",
    "load_pipelex_service_config_if_exists",
]
