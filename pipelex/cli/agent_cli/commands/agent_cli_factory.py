"""Factory function for agent CLI commands -- JSON-only error output."""

import warnings
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, record_setup_warning
from pipelex.cogt.exceptions import GatewayUnknownModelError, ModelDeckPresetValidatonError
from pipelex.hub import PipelexHub
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
# on stderr AND all pipelex logs are silenced from the very first ``log.configure`` call."
# Consumed by:
#   - ``AGENT_CLI_CONFIG_OVERRIDES`` below wraps it in the full-config-tree shape required
#     by ``Pipelex.make(config_overrides=...)`` for the full-init path.
#   - ``pipelex.cli.agent_cli.commands.doctor_cmd`` passes it flat to
#     ``setup_doctor_runtime(log_config_overrides=...)`` for the doctor-only path that
#     does not go through ``Pipelex.make``.
#
# Four knobs:
#   - ``console_log_target``  -> the ``RichHandler`` for Python's logging system
#                                (``log.debug/info/warning/error``).
#   - ``console_print_target`` -> the ``Console`` returned by ``get_console()`` and used
#                                for banners, deck notices, and the main ``pipelex`` CLI's
#                                ``show backends`` / ``show models`` tables.
#   - ``default_log_level``   -> root-logger level. Pinned at OFF so any third-party
#                                package that inherits root (no explicit override) is
#                                fully silenced.
#   - ``package_log_levels``  -> per-package overrides. ``pipelex`` is pinned at OFF here;
#                                deep-merged into the user's config, so third-party
#                                package levels (anthropic, asyncio, ...) are preserved.
#
# Why silence all pipelex logs? The agent CLI is machine-consumed. Its contract is:
# stdout = structured success envelope (JSON or markdown), stderr = structured error
# envelope. ANY log line on stderr — DEBUG, INFO, WARNING, anything — corrupts the
# error-envelope channel for downstream parsers (e.g. mthds-js's ``PipelexRunner``
# doing ``JSON.parse(stderr)``). This is not a verbosity setting; it's the design.
# There is no ``--log-level`` escape hatch on ``pipelex-agent``: when debugging is
# needed, use the human ``pipelex`` CLI instead.
#
# The agent CLI's actual results are written by ``agent_success`` /
# ``agent_success_formatted`` via the bare builtin ``print(...)`` to ``sys.stdout``;
# error envelopes via ``print(..., file=sys.stderr)``. Both bypass Rich entirely, so
# the OFF-level pin has no effect on the structured envelopes — only on free-floating
# ``log.*`` calls scattered through the codebase.
#
# Wrapped in ``MappingProxyType`` so a stray ``AGENT_CLI_STDERR_LOG_FIELDS[...] = ...`` in
# a future contributor's hot-fix raises immediately instead of silently mutating the
# shared canonical instance.
AGENT_CLI_STDERR_LOG_FIELDS: Mapping[str, Any] = MappingProxyType(
    {
        "console_log_target": ConsoleTarget.STDERR,
        "console_print_target": ConsoleTarget.STDERR,
        "default_log_level": LogLevel.OFF,
        "package_log_levels": MappingProxyType({"pipelex": LogLevel.OFF}),
    }
)

# Full ``config_overrides`` tree for ``Pipelex.make()``. ``deep_update`` recurses into
# ``package_log_levels``, so the ``pipelex = OFF`` entry merges into the user's config
# without wiping out third-party package levels. Frozen so callers can't mutate it.
AGENT_CLI_CONFIG_OVERRIDES: Mapping[str, Any] = MappingProxyType(
    {
        "pipelex": MappingProxyType(
            {
                "log_config": AGENT_CLI_STDERR_LOG_FIELDS,
            },
        ),
    }
)


def apply_agent_cli_output_discipline() -> None:
    """Pin pipelex log level to OFF, silence pretty-print, and hub console target to stderr.

    Called from two paths:
      - ``make_pipelex_for_agent_cli`` (full-init): defense-in-depth. ``Pipelex.__init__``
        already pinned the hub console via ``set_console_print_target`` from the loaded
        log_config (whose ``console_print_target`` was overridden to STDERR by
        ``AGENT_CLI_CONFIG_OVERRIDES``, which also pinned the pipelex log level to OFF).
      - ``agent_doctor_cmd`` (doctor-only): also defense-in-depth, since
        ``setup_doctor_runtime`` now mirrors ``Pipelex.__init__`` and applies
        ``set_console_print_target`` itself from the overridden log_config.

    Safe to call from the broken-config doctor path where ``setup_doctor_runtime`` was
    skipped: ``log.redirect_to_stderr`` no-ops when no rich_handler is registered, and
    the hub print-target call is gated on a hub being installed.
    """
    log.set_level_for_package("pipelex", LogLevel.OFF)
    log.redirect_to_stderr()
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    hub = PipelexHub.get_optional_instance()
    if hub is not None:
        hub.set_console_print_target(target=ConsoleTarget.STDERR)


def make_pipelex_for_agent_cli(
    library_dirs: list[str] | list[Path] | None = None,
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

    Stdout / stderr contract: every ``pipelex-agent`` invocation reserves stdout
    exclusively for the structured success envelope (JSON via ``--format json``, or
    markdown via ``--format markdown``) emitted by ``agent_success`` /
    ``agent_success_formatted``, and stderr exclusively for the structured error
    envelope from ``agent_error``. NO free-floating logs are emitted on either channel,
    regardless of what the user's ``pipelex.toml`` says. The factory enforces this via:

      1. ``AGENT_CLI_CONFIG_OVERRIDES`` injected into ``Pipelex.make()`` pins
         ``console_log_target`` and ``console_print_target`` to ``stderr`` AND silences
         pipelex's logs (``default_log_level = OFF``, ``package_log_levels.pipelex = OFF``)
         from the very first ``log.configure`` call — so DEBUG/INFO/WARNING setup chatter
         (e.g. ``telemetry_factory.py``'s ``log.debug``, ``validation_error_categorizer``'s
         ``log.warning``) never reaches the handler, even when the user's
         ``~/.pipelex/pipelex.toml`` sets ``pipelex = "DEBUG"``.
      2. ``PrettyPrinter.mode = SILENT`` neutralizes ``pretty_print(...)`` entirely.
      3. Post-init ``log.redirect_to_stderr()`` and
         ``get_pipelex_hub().set_console_print_target(STDERR)`` defense-in-depth.

    Args:
        library_dirs: Optional library directories to use for the Pipelex instance.
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
                config_overrides=dict(AGENT_CLI_CONFIG_OVERRIDES),
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

    # Silence pipelex logs and Rich pretty-printing so the agent CLI emits only the
    # structured success/error envelope. Defense-in-depth on top of the init-time
    # config_overrides.
    apply_agent_cli_output_discipline()
    return pipelex_instance
