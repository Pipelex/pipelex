"""Factory functions for CLI commands."""

from pathlib import Path

from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_gateway_api_key_missing_error,
    handle_gateway_do_not_track_conflict_error,
    handle_gateway_terms_not_accepted_error,
    handle_model_deck_preset_error,
    handle_remote_config_fetch_error,
    handle_remote_config_validation_error,
    handle_telemetry_config_validation_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError


def make_pipelex_for_cli(context: ErrorContext, library_dirs: list[str] | list[Path] | None = None) -> Pipelex:
    """Initialize Pipelex for CLI commands with proper error handling.

    This is a DRY wrapper around Pipelex.make() that catches common errors
    and displays user-friendly messages with guidance.

    Args:
        context: The CLI context for error messages.
        library_dirs: The library directories to use for the Pipelex instance.

    Returns:
        Initialized Pipelex instance.

    Raises:
        typer.Exit: If initialization fails with a handled error.
    """
    try:
        return Pipelex.make(integration_mode=IntegrationMode.CLI, library_dirs=library_dirs)
    except TelemetryConfigValidationError as exc:
        handle_telemetry_config_validation_error(exc)
    except GatewayTermsNotAcceptedError as exc:
        handle_gateway_terms_not_accepted_error(exc)
    except GatewayApiKeyMissingError as exc:
        handle_gateway_api_key_missing_error(exc)
    except GatewayDoNotTrackConflictError as exc:
        handle_gateway_do_not_track_conflict_error(exc)
    except RemoteConfigFetchError as exc:
        handle_remote_config_fetch_error(exc)
    except RemoteConfigValidationError as exc:
        handle_remote_config_validation_error(exc)
    except ModelDeckPresetValidatonError as exc:
        handle_model_deck_preset_error(exc, context=context)
