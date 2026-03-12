"""Factory function for agent CLI commands -- JSON-only error output."""

from pathlib import Path

from pipelex.cli.agent_cli.commands.agent_output import agent_error
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
from pipelex.tools.log.log import log
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode


def make_pipelex_for_agent_cli(
    library_dirs: list[str] | list[Path] | None = None,
    log_level: LogLevel = LogLevel.WARNING,
    needs_inference: bool = True,
    needs_model_specs: bool | None = None,
) -> Pipelex:
    """Initialize Pipelex for agent CLI commands with JSON error output.

    This is the agent CLI counterpart of ``make_pipelex_for_cli`` in
    ``pipelex.cli.cli_factory``.  It catches the same initialization
    exceptions but routes them through ``agent_error()`` so the output
    is always machine-parseable JSON on stderr.

    Args:
        library_dirs: Optional library directories to use for the Pipelex instance.
        log_level: Log verbosity level (default WARNING for silent agent output).
        needs_inference: When False, skip inference setup (credentials, gateway, telemetry).
        needs_model_specs: When True, load real model specs even without inference.

    Returns:
        Initialized Pipelex instance.

    Raises:
        typer.Exit: If initialization fails (after printing JSON error to stderr).
    """
    try:
        pipelex_instance = Pipelex.make(
            integration_mode=IntegrationMode.CLI, library_dirs=library_dirs, needs_inference=needs_inference, needs_model_specs=needs_model_specs
        )
    except TelemetryConfigValidationError as exc:
        agent_error(exc.message, "TelemetryConfigValidationError", cause=exc)
    except GatewayTermsNotAcceptedError as exc:
        agent_error(exc.message, "GatewayTermsNotAcceptedError", cause=exc)
    except GatewayApiKeyMissingError as exc:
        agent_error(exc.message, "GatewayApiKeyMissingError", cause=exc)
    except GatewayDoNotTrackConflictError as exc:
        agent_error(exc.message, "GatewayDoNotTrackConflictError", cause=exc)
    except RemoteConfigFetchError as exc:
        agent_error(exc.message, "RemoteConfigFetchError", cause=exc)
    except RemoteConfigValidationError as exc:
        agent_error(exc.message, "RemoteConfigValidationError", cause=exc)
    except ModelDeckPresetValidatonError as exc:
        agent_error(
            exc.message,
            "ModelDeckPresetValidatonError",
            cause=exc,
            preset_id=exc.preset_id,
            model_type=str(exc.model_type),
            model_handle=exc.model_handle,
            enabled_backends=sorted(exc.enabled_backends),
        )
    except Exception as exc:
        agent_error(
            f"Pipelex initialization failed: {exc}",
            type(exc).__name__,
            cause=exc,
            hint="Initialization failed. Run 'pipelex-agent doctor' to diagnose, or 'pipelex init config' to reset configuration",
        )

    # Suppress Rich pretty-printing and INFO/DEV/DEBUG log noise so that agent
    # commands only emit structured JSON.  Warnings and errors still reach stderr.
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    log.set_level_for_package("pipelex", log_level)
    log.redirect_to_stderr()
    return pipelex_instance
