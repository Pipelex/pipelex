"""Factory function for agent CLI commands -- JSON-only error output."""

import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import RuntimeHub
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.log.log import log
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode

# Canonical leaf dict for "for any agent-CLI invocation, both Rich-managed channels land
# on stderr AND Python's logging system is globally muted from the very first init call."
# Consumed by:
#   - ``AGENT_CLI_CONFIG_OVERRIDES`` below wraps it in the full-config-tree shape required
#     by ``Pipelex.make(config_overrides=...)`` for the full-init path.
#   - ``pipelex.cli.agent_cli.commands.doctor_cmd`` passes it flat to
#     ``setup_doctor_runtime(log_config_overrides=...)`` for the doctor-only path that
#     does not go through ``Pipelex.make``.
#
# The knobs in this dict shape Pipelex's own log infrastructure but they CANNOT
# enumerate every third-party logger a transitive dependency might create. The
# bulletproof cutoff lives in ``silence_logging_for_agent_cli`` below, which calls
# ``logging.disable(sys.maxsize)`` — a process-global threshold checked inside
# ``Logger.isEnabledFor`` BEFORE any per-logger level. With that in effect, no record
# is created for any logger, regardless of which package emits, how it's configured, or
# what handlers it attaches. We call it as the very first line of
# ``make_pipelex_for_agent_cli`` and ``agent_doctor_cmd`` so the cutoff is active before
# any setup code can reach a ``log.*`` call.
#
# The dict below stays useful as defense-in-depth + Rich-channel pinning:
#   - ``console_log_target``  -> the ``RichHandler`` for Python's logging system
#                                (``log.debug/info/warning/error``). Pinned to stderr so
#                                if ``logging.disable`` is ever cleared in this process,
#                                logs still land on the diagnostic channel rather than
#                                corrupting the stdout success envelope.
#   - ``console_print_target`` -> the ``Console`` returned by ``get_console()`` and used
#                                for banners, deck notices, and the main ``pipelex`` CLI's
#                                ``show backends`` / ``show models`` tables. Rich Console
#                                is INDEPENDENT of Python logging — ``logging.disable``
#                                does not touch it — so this pin is the only thing
#                                keeping Rich tables off stdout.
#   - ``pretty_print_mode``    -> the ``PrettyPrinter`` behind ``pretty_print(...)``, the
#                                "Output of pipe" panels among them. Pinned to silent so
#                                no Rich panel is built or printed at all.
#   - ``default_log_level``   -> root-logger level. Pinned at OFF as a backup in case
#                                ``logging.disable`` is cleared.
#   - ``package_log_levels``  -> historic ``pipelex = OFF`` pin. Redundant under
#                                ``logging.disable`` but kept as defense.
#
# Why silence everything? The agent CLI is machine-consumed. Its contract is:
# stdout = structured success envelope (JSON or markdown), stderr = structured error
# envelope. ANY log line on stderr — DEBUG, INFO, WARNING, anything — corrupts the
# error-envelope channel for downstream parsers (e.g. mthds-js's ``PipelexMTHDSProtocol``
# doing ``JSON.parse(stderr)``). This is not a verbosity setting; it's the design.
# There is no ``--log-level`` escape hatch on ``pipelex-agent``: when debugging is
# needed, use the human ``pipelex`` CLI instead.
#
# The agent CLI's actual results are written by ``agent_success`` /
# ``agent_success_formatted`` via the bare builtin ``print(...)`` to ``sys.stdout``;
# error envelopes via ``print(..., file=sys.stderr)``. Both bypass Rich and Python's
# ``logging`` entirely, so neither ``logging.disable`` nor the pins below affect the
# structured envelopes themselves.
#
# Wrapped in ``MappingProxyType`` so a stray ``AGENT_CLI_STDERR_LOG_FIELDS[...] = ...`` in
# a future contributor's hot-fix raises immediately instead of silently mutating the
# shared canonical instance.
AGENT_CLI_STDERR_LOG_FIELDS: Mapping[str, Any] = MappingProxyType(
    {
        "console_log_target": ConsoleTarget.STDERR,
        "console_print_target": ConsoleTarget.STDERR,
        "pretty_print_mode": PrettyPrintMode.SILENT,
        "default_log_level": LogLevel.OFF,
        "package_log_levels": MappingProxyType({"pipelex": LogLevel.OFF}),
    }
)


def silence_logging_for_agent_cli() -> None:
    """Process-global cutoff of Python's logging system for agent CLI invocations.

    Calls ``logging.disable(sys.maxsize)``, which sets
    ``logging.Logger.manager.disable = sys.maxsize``. Every ``Logger.isEnabledFor``
    call checks ``self.manager.disable >= level`` before the per-logger level check, so
    no record gets created for any logger — blocks every record at every level
    (including custom levels above CRITICAL), regardless of which package emits, what
    level the logger is configured at, or what handlers it has attached. This includes
    third-party packages we never enumerate and any logger created AFTER this call.

    Idempotent. The primary call site is ``app_callback`` in
    ``pipelex.cli.agent_cli._agent_cli`` — Typer routes every ``pipelex-agent``
    subcommand through that callback, so the cutoff is armed before any command body
    runs (including commands like ``init`` that bypass
    ``make_pipelex_for_agent_cli``). The additional invocations at the top of
    ``make_pipelex_for_agent_cli`` and ``agent_doctor_cmd`` are belt-and-braces
    defense for direct library callers that bypass the Typer entry point (and for
    the unit tests that drive those factories directly).

    Does NOT affect Rich ``Console`` output (banners, tables, pretty_print) — that's
    handled by ``console_print_target = STDERR`` + ``PrettyPrinter.mode = SILENT`` +
    the hub's ``set_console_print_target``. Does NOT affect bare ``print(...)`` calls
    — those are reserved for the structured success/error envelopes by design.
    """
    logging.disable(sys.maxsize)


# Full ``config_overrides`` tree for ``Pipelex.make()``. ``deep_update`` recurses into
# ``package_log_levels``, so the ``pipelex = OFF`` entry merges into the user's config
# without wiping out third-party package levels. Frozen so callers can't mutate it.
AGENT_CLI_CONFIG_OVERRIDES: Mapping[str, Any] = MappingProxyType(
    {
        "runtime": MappingProxyType(
            {
                "log": AGENT_CLI_STDERR_LOG_FIELDS,
            },
        ),
    }
)


#: The next step of a boot that failed, and of any other failure to read this machine's configuration. It names only
#: commands an agent can run: `pipelex init config` asks questions and can open a browser.
AGENT_INIT_FAILURE_HINT = (
    "Initialization failed. Run 'pipelex-agent doctor' to diagnose. An out-of-date configuration is brought up to date by "
    "'pipelex-agent migrate --dry-run --format json', shown to the user, then 'pipelex-agent migrate --yes'; "
    "'pipelex-agent init' (--global for the home configuration) writes a fresh one instead, discarding its settings"
)


def apply_agent_cli_output_discipline() -> None:
    """Reaffirm the agent CLI output contract on the Rich/hub channels post-init.

    The bulletproof logging cutoff is ``silence_logging_for_agent_cli`` (called at the
    start of every agent CLI entry point); this helper handles the channels that are
    INDEPENDENT of Python's logging system:

      1. ``log.redirect_to_stderr`` points the installed sink at stderr when it writes to a
         process stream — defense in case ``logging.disable`` is ever cleared.
      2. ``PrettyPrinter.mode = SILENT`` neutralizes ``pretty_print(...)`` entirely
         (Rich-based, not logging-based).
      3. Hub-level ``set_console_print_target(STDERR)`` for the Rich ``Console`` used by
         banners / tables (also Rich-based, not logging-based).

    Safe to call from the broken-config doctor path where ``setup_doctor_runtime`` was
    skipped: ``log.redirect_to_stderr`` no-ops before a sink is installed, a sink that
    writes to no process stream ignores it, and the hub print-target call is gated on a
    hub being installed.
    """
    log.redirect_to_stderr()
    PrettyPrinter.mode = PrettyPrintMode.SILENT
    hub = RuntimeHub.get_optional_instance()
    if hub is not None:
        hub.set_console_print_target(target=ConsoleTarget.STDERR)


def make_pipelex_for_agent_cli(*, library_dirs: list[str] | list[Path] | None = None, needs_inference: bool = True) -> Pipelex:
    """Initialize Pipelex for agent CLI commands with JSON error output.

    This is the agent CLI counterpart of ``make_pipelex_for_cli`` in
    ``pipelex.cli.cli_factory``.  It catches the same initialization
    exceptions but routes them through ``agent_error()`` so the output
    is always machine-parseable JSON on stderr.

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
         ``get_runtime_hub().set_console_print_target(STDERR)`` defense-in-depth.

    Args:
        library_dirs: Optional library directories to use for the Pipelex instance.
        needs_inference: When False, boot without inference: every enabled backend and its models
            load, no credential is resolved, and every run this process starts is forced to DRY.

    Returns:
        Initialized Pipelex instance.

    Raises:
        typer.Exit: If initialization fails (after printing JSON error to stderr).
    """
    # Process-global logging cutoff, BEFORE Pipelex.make can trigger any third-party
    # log line (anthropic/httpx/botocore credential probes, telemetry setup, etc.).
    silence_logging_for_agent_cli()
    try:
        pipelex_instance = Pipelex.make(
            integration_mode=IntegrationMode.CLI,
            library_dirs=library_dirs,
            needs_inference=needs_inference,
            config_overrides=dict(AGENT_CLI_CONFIG_OVERRIDES),
        )
    except TelemetryConfigValidationError as exc:
        agent_error(exc.message, error_type="TelemetryConfigValidationError", cause=exc)
    except FormerReleaseConfigError as exc:
        # Its own hint, the class's user_action, rather than the generic one, which offers a reset: the cleanup keeps
        # everything but what a former release left, and an agent can run it.
        agent_error(exc.message, error_type="FormerReleaseConfigError", cause=exc)
    except ModelDeckPresetValidatonError as exc:
        agent_error(
            exc.message,
            error_type="ModelDeckPresetValidatonError",
            cause=exc,
            preset_id=exc.preset_id,
            model_type=str(exc.model_type),
            model_handle=exc.model_handle,
            enabled_backends=sorted(exc.enabled_backends),
        )
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(
            f"Pipelex initialization failed: {exc}",
            error_type=type(exc).__name__,
            cause=exc,
            hint=AGENT_INIT_FAILURE_HINT,
        )

    # Silence pipelex logs and Rich pretty-printing so the agent CLI emits only the
    # structured success/error envelope. Defense-in-depth on top of the init-time
    # config_overrides.
    apply_agent_cli_output_discipline()
    return pipelex_instance
