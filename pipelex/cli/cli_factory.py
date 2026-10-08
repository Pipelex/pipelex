"""Factory functions for CLI commands."""

from pathlib import Path

from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_former_release_config_error,
    handle_model_deck_preset_error,
    handle_telemetry_config_validation_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError


def make_pipelex_for_cli(
    *,
    context: ErrorContext,
    library_dirs: list[str] | list[Path] | None = None,
    needs_inference: bool = True,
    boot_orchestrator: str | None = None,
) -> Pipelex:
    """Initialize Pipelex for CLI commands with proper error handling.

    This is a DRY wrapper around Pipelex.make() that catches common errors
    and displays user-friendly messages with guidance.

    Args:
        context: The CLI context for error messages.
        library_dirs: The library directories to use for the Pipelex instance.
        needs_inference: When False, boot without inference: every enabled backend and its models
            load, no credential is resolved, and every run this process starts is forced to DRY.
        boot_orchestrator: When provided, boots this process under the orchestrator plugin of this name.

    Returns:
        Initialized Pipelex instance.

    Raises:
        typer.Exit: If initialization fails with a handled error.
    """
    try:
        return Pipelex.make(
            integration_mode=IntegrationMode.CLI,
            library_dirs=library_dirs,
            needs_inference=needs_inference,
            boot_orchestrator=boot_orchestrator,
        )
    except TelemetryConfigValidationError as exc:
        handle_telemetry_config_validation_error(exc)
    except ModelDeckPresetValidatonError as exc:
        handle_model_deck_preset_error(exc, context=context)
    except FormerReleaseConfigError as exc:
        handle_former_release_config_error(exc=exc)
