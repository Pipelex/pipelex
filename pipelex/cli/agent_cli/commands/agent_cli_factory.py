"""Factory function for agent CLI commands -- JSON-only error output."""

import warnings
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, record_setup_warning
from pipelex.cogt.exceptions import GatewayUnknownModelError, ModelDeckPresetValidatonError
from pipelex.hub import get_pipelex_hub
from pipelex.pipelex import Pipelex
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    InferenceSetupRequiredError,
    RemoteConfigStaleWarning,
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.log.log import log
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode

# Canonical leaf dict for "for any agent-CLI invocation, both Rich-managed channels land
# on stderr." Composed by two distinct call sites:
#   - ``_AGENT_CLI_STDERR_CONSOLE_OVERRIDES`` below wraps it in the full-config-tree shape
#     required by ``Pipelex.make(config_overrides=...)`` for the full-init path.
#   - ``pipelex.cli.agent_cli.commands.doctor_cmd`` passes it flat to
#     ``setup_doctor_runtime(log_config_overrides=...)`` for the doctor-only path that
#     does not go through ``Pipelex.make``.
#
# These two knobs only control Rich-managed diagnostic channels — NOT the agent CLI's
# data channel:
#   - ``console_log_target``  -> the ``RichHandler`` for Python's logging system
#                                (``log.debug/info/warning/error``).
#   - ``console_print_target`` -> the ``Console`` returned by ``get_console()`` and used
#                                for banners, deck notices, and the main ``pipelex`` CLI's
#                                ``show backends`` / ``show models`` tables.
#
# The agent CLI's actual results (the JSON / markdown success envelope) are written by
# ``agent_success`` / ``agent_success_formatted`` in ``agent_output.py`` via the bare
# builtin ``print(...)`` straight to ``sys.stdout``. They do NOT go through Rich, so they
# are unaffected by these overrides. Error envelopes go via ``print(..., file=sys.stderr)``
# — also bypassing Rich.
#
# Pinning both targets to ``stderr`` therefore ensures that EVERYTHING ELSE Pipelex might
# emit (setup-time ``log.debug`` from ``telemetry_factory.py``, a banner from
# ``deck_notice.py``, any future ``get_console().print(...)`` on the agent CLI setup path)
# lands on stderr regardless of what the user's ``~/.pipelex/pipelex.toml`` says — so the
# JSON data channel on stdout stays clean for downstream consumers like ``mthds-js``'s
# ``PipelexRunner`` that do ``JSON.parse(stdout)``.
#
# Wrapped in ``MappingProxyType`` so a stray ``AGENT_CLI_STDERR_LOG_FIELDS[...] = ...`` in
# a future contributor's hot-fix raises immediately instead of silently mutating the
# shared canonical instance (which both consumers below alias).
AGENT_CLI_STDERR_LOG_FIELDS: Mapping[str, Any] = MappingProxyType(
    {
        "console_log_target": ConsoleTarget.STDERR,
        "console_print_target": ConsoleTarget.STDERR,
    }
)

# deep_update only recurses into ``dict`` instances; ``MappingProxyType`` would short-
# circuit and overwrite the whole log_config branch. Build the override tree with a real
# dict copy of the canonical leaf so the merge keeps merging.
_AGENT_CLI_STDERR_CONSOLE_OVERRIDES: dict[str, Any] = {
    "pipelex": {"log_config": dict(AGENT_CLI_STDERR_LOG_FIELDS)},
}


def apply_agent_cli_output_discipline(log_level: LogLevel = LogLevel.WARNING) -> None:
    """Pin pipelex log level, pretty-print silence, and hub console target to stderr.

    Called from two paths:
      - ``make_pipelex_for_agent_cli`` (full-init): defense-in-depth. ``Pipelex.__init__``
        already pinned the hub console via ``set_console_print_target`` from the loaded
        log_config (whose ``console_print_target`` was overridden to STDERR by
        ``_AGENT_CLI_STDERR_CONSOLE_OVERRIDES``).
      - ``agent_doctor_cmd`` (doctor-only): also defense-in-depth, since
        ``setup_doctor_runtime`` now mirrors ``Pipelex.__init__`` and applies
        ``set_console_print_target`` itself from the overridden log_config.

    Folding ``log.set_level_for_package("pipelex", log_level)`` in here keeps every
    agent CLI command sharing one source of truth for "be quiet on stderr."

    Args:
        log_level: Floor for the ``pipelex`` package logger. Defaults to WARNING so the
            agent CLI surface stays terse; the factory passes its own ``log_level``
            through unchanged.
    """
    log.set_level_for_package("pipelex", log_level)
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    get_pipelex_hub().set_console_print_target(target=ConsoleTarget.STDERR)


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

    One intentional exception: ``InferenceSetupRequiredError`` prints
    human-readable markdown to stdout and exits 0, so the calling agent
    can display setup guidance directly.

    Stdout contract: every ``pipelex-agent`` invocation reserves stdout exclusively
    for the structured success envelope (JSON via ``--format json``, or markdown via
    ``--format markdown``) emitted by ``agent_success`` / ``agent_success_formatted``.
    All other output channels — logs, ``get_console().print(...)`` output, Rich pretty
    prints, and ``agent_error`` envelopes — are pinned to stderr regardless of what the
    user's ``pipelex.toml`` says. The factory enforces this via three layers:

      1. ``config_overrides`` injected into ``Pipelex.make()`` pins both
         ``console_log_target`` and ``console_print_target`` to ``stderr`` from the
         very first log/print fired during init.
      2. ``PrettyPrinter.mode = SILENT`` neutralizes ``pretty_print(...)`` entirely.
      3. Post-init ``log.redirect_to_stderr()`` and
         ``get_pipelex_hub().set_console_print_target(STDERR)`` defense-in-depth.

    Args:
        library_dirs: Optional library directories to use for the Pipelex instance.
        log_level: Log verbosity level (default WARNING for silent agent output).
        needs_inference: When False, skip inference setup (credentials, gateway, telemetry).
        needs_model_specs: When True, load real model specs even without inference.

    Returns:
        Initialized Pipelex instance.

    Raises:
        typer.Exit: If initialization fails (after printing JSON error to stderr),
            or if inference setup is required (after printing markdown to stdout).
    """
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RemoteConfigStaleWarning)
            pipelex_instance = Pipelex.make(
                integration_mode=IntegrationMode.CLI,
                library_dirs=library_dirs,
                needs_inference=needs_inference,
                needs_model_specs=needs_model_specs,
                config_overrides=_AGENT_CLI_STDERR_CONSOLE_OVERRIDES,
            )
        # Surface a structured ``RemoteConfigStale`` entry so JSON consumers can react to
        # stale-cache operation without parsing stderr.
        for item in caught:
            if issubclass(item.category, RemoteConfigStaleWarning):
                record_setup_warning({"type": "RemoteConfigStale", "message": str(item.message)})
    except InferenceSetupRequiredError:
        print(
            "# First-time inference setup required\n"
            "\n"
            "This looks like your first time running a method with live inference.\n"
            "You need to configure an inference backend before running.\n"
            "\n"
            "Use `/mthds-runner-setup` for guided setup, "
            "or run `pipelex-agent init` with appropriate backend configuration."
        )
        raise typer.Exit(0) from None
    except TelemetryConfigValidationError as exc:
        agent_error(exc.message, "TelemetryConfigValidationError", cause=exc)
    except GatewayTermsNotAcceptedError as exc:
        agent_error(exc.message, "GatewayTermsNotAcceptedError", cause=exc)
    except GatewayApiKeyMissingError as exc:
        agent_error(exc.message, "GatewayApiKeyMissingError", cause=exc)
    except GatewayDoNotTrackConflictError as exc:
        agent_error(exc.message, "GatewayDoNotTrackConflictError", cause=exc)
    except RemoteConfigUnavailableError as exc:
        agent_error(exc.message, "RemoteConfigUnavailableError", cause=exc)
    except RemoteConfigValidationError as exc:
        agent_error(exc.message, "RemoteConfigValidationError", cause=exc)
    except GatewayUnknownModelError as exc:
        agent_error(
            exc.message,
            "GatewayUnknownModelError",
            cause=exc,
            model_name=exc.model_name,
            source=exc.source,
        )
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
    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(
            f"Pipelex initialization failed: {exc}",
            type(exc).__name__,
            cause=exc,
            hint="Initialization failed. Run 'pipelex-agent doctor' to diagnose, or 'pipelex init config' to reset configuration",
        )

    # Suppress Rich pretty-printing and INFO/DEV/DEBUG log noise so that agent
    # commands only emit structured JSON.  Warnings and errors still reach stderr.
    log.redirect_to_stderr()
    apply_agent_cli_output_discipline(log_level=log_level)
    return pipelex_instance
