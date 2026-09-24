"""Exceptions for Pipelex managed services."""

from pipelex.base_exceptions import ErrorDomain
from pipelex.system.exceptions import PipelexError


class PipelexServiceConfigValidationError(PipelexError):
    """Raised when pipelex_service.toml validation fails."""

    error_domain = ErrorDomain.CONFIG


class PipelexServiceError(PipelexError):
    """Base exception for Pipelex service errors."""

    error_domain = ErrorDomain.CONFIG


class RemoteConfigFetchError(PipelexServiceError):
    """Raised when fetching the Pipelex remote configuration fails.

    This error occurs when:
    - The network request fails
    - The server answers with an error status
    """


class RemoteConfigValidationError(PipelexServiceError):
    """Raised when remote configuration payload validation fails.

    This error occurs when:
    - JSON payload is not valid
    - Payload structure doesn't match expected schema
    """


class RemoteConfigUnavailableError(PipelexServiceError):
    """Raised when a fresh fetch failed AND no usable cached fallback exists.

    This is the user-facing offline-mode error: a Pipelex-managed gateway backend is enabled but we
    have neither a working network path nor a primed local cache to fall back on. The message names
    the cache file path and the remediation (``pipelex init`` while online; or disabling the managed
    backend in ``backends.toml`` for permanent offline operation).
    """


class RemoteConfigStaleWarning(UserWarning):
    """Emitted when setup completes using a cached remote-config fallback instead of a fresh fetch.

    Indicates the network was unreachable but a prior ``pipelex init`` had primed the cache.
    Stale operation is intentionally safe for dry-run/validation flows; real inference calls
    still require network at call time.
    """


class InferenceSetupRequiredError(PipelexServiceError):
    """Raised when inference is requested but no inference setup has been completed.

    This is the first-run signal: the user has not yet configured any
    inference backend. The agent skill should catch this
    error type and guide the user through the onboarding flow.
    """

    def __init__(self) -> None:
        msg = (
            "Inference setup required.\n"
            "This looks like your first time running a method with live inference.\n"
            "You need to configure an inference backend before running.\n"
            "Use /mthds-runner-setup for guided setup,\n"
            "or run `pipelex-agent init` with appropriate backend configuration."
        )
        super().__init__(msg)


class GatewayOverrideWarning(UserWarning):
    """Warning issued when local overrides are applied to a managed gateway's served model specs."""


class GatewayConfigMergeError(PipelexServiceError):
    """Raised when merging a managed gateway's served model specs with local overrides meets invalid data.

    This error occurs when:
    - Local override for a model is not a dictionary
    - Remote config for a model is not a dictionary
    """
