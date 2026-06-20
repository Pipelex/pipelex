import importlib
from typing import Annotated

import typer
from click import Command, Context
from pydantic import ValidationError
from typer.core import TyperGroup
from typing_extensions import override

from pipelex import log
from pipelex.cli.commands.build.app import build_app
from pipelex.cli.commands.doctor_cmd import doctor_cmd
from pipelex.cli.commands.graph_cmd import graph_app
from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.login.command import login_cmd
from pipelex.cli.commands.plugins_cmd import plugins_app
from pipelex.cli.commands.run.app import run_app
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.update_cmd import update_cmd
from pipelex.cli.commands.validate.app import validate_app
from pipelex.cli.commands.which_cmd import which_cmd
from pipelex.cli.deck_notice import warn_if_deck_stale
from pipelex.cli.error_handlers import set_traceback_requested
from pipelex.cli.readiness import check_readiness
from pipelex.hub import get_console
from pipelex.plugins.discovery import build_registrar
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.package_utils import get_package_version

# Core commands in display order (natural ordering doesn't work between Typer groups and commands).
# Plugin-contributed commands (e.g. Temporal's ``worker`` / ``setup-temporal-namespace``) are appended
# after these, in discovery order — see ``_register_discovered_cli_commands``.
_CORE_COMMAND_ORDER: list[str] = [
    "login",
    "init",
    "doctor",
    "update",
    "build",
    "validate",
    "run",
    "graph",
    "show",
    "which",
    "plugins",
]


class PipelexCLI(TyperGroup):
    """Custom CLI group that handles global options like --no-logo."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        return [*_CORE_COMMAND_ORDER, *_PLUGIN_COMMAND_NAMES]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd

    @override
    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Context | None = None,
        **extra: object,
    ) -> Context:
        """Intercept global flags from args before Click/Typer processes them.

        This allows --no-logo and --traceback to be placed anywhere in the
        command line (before or after subcommands) while keeping the CLI
        architecture clean.
        """
        no_logo = "--no-logo" in args
        if no_logo:
            args = [arg for arg in args if arg != "--no-logo"]

        traceback = "--traceback" in args
        if traceback:
            args = [arg for arg in args if arg != "--traceback"]

        ctx = super().make_context(info_name, args, parent, **extra)
        ctx.ensure_object(dict)
        ctx.obj["no_logo"] = no_logo
        ctx.obj["traceback"] = traceback
        # Record at parse time so error handlers honor --traceback without relying on
        # an active global Click context (absent under typer >= 0.26 / click >= 8.4).
        set_traceback_requested(traceback)
        return ctx


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


def version_callback(value: bool) -> None:
    """Print version and exit when --version is passed."""
    if value:
        package_version = get_package_version()
        typer.echo(f"pipelex {package_version}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    version: Annotated[  # noqa: ARG001
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    console = get_console()
    package_version = get_package_version()

    # Get no_logo flag from context (set by PipelexCLI.make_context). Use the
    # ctx parameter Typer injects rather than click.get_current_context(): the
    # global context stack is not populated when a subcommand is dispatched
    # under typer >= 0.26 / click >= 8.4, which made every subcommand crash.
    no_logo = ctx.obj.get("no_logo", False) if ctx.obj else False

    if no_logo:
        console.print(f"Pipelex v{package_version}")
    else:
        console.print(
            f"""

░█████████  ░[bold green4]██[/bold green4]                      ░██
░██     ░██                          ░██
░██     ░██ ░██░████████   ░███████  ░██  ░███████  ░██    ░[bold green4]██[/bold green4]
░█████████  ░██░██    ░██ ░██    ░██ ░██ ░██    ░██  ░██  ░██
░██         ░██░██    ░██ ░█████████ ░██ ░█████████   ░█████
░██         ░██░███   ░██ ░██        ░██ ░██         ░██  ░██
░██         ░██░██░█████   ░███████  ░██  ░███████  ░██    ░██
               ░██
               ░██                                     v[cyan]{package_version}[/cyan]
"""
        )
    # Skip checks if no command is being run (e.g., just --help) or if running setup/diagnostic commands
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand in {"login", "init", "doctor", "update", "which"}:
        return

    # Check system readiness (dependencies and venv for dev installs)
    check_readiness()

    # Warn if the model deck has fallen behind the installed pipelex version
    warn_if_deck_stale()


@app.command(name="login", help="Log in to Pipelex Gateway via the browser and save your API key")
def login_command() -> None:
    """Open the browser to authenticate and save your Pipelex Gateway API key."""
    login_cmd()


@app.command(name="init", help="Initialize Pipelex configuration, backends, credentials, routing, and telemetry")
def init_command(
    focus: Annotated[
        InitFocus,
        typer.Argument(
            help="What to initialize: 'all' (default), 'config', 'credentials', 'inference', 'routing', 'telemetry', or 'agreement'",
        ),
    ] = InitFocus.ALL,
    local: Annotated[
        bool, typer.Option("--local", "-l", help="Create project-level .pipelex/ at the detected project root instead of global ~/.pipelex/")
    ] = False,
) -> None:
    """Initialize Pipelex configuration in ~/.pipelex (global) or project .pipelex (--local).

    Focus options:

      all          Full setup: config files, backends, credentials, routing, telemetry (default)

      config       Reset configuration files and prompt for missing API keys

      credentials  Prompt for missing API keys only (reads enabled backends, saves to ~/.pipelex/.env)

      inference    Reset inference backends selection and prompt for missing API keys

      routing      Reset routing profile

      telemetry    Reset telemetry preferences

      agreement    Review/accept Pipelex Gateway terms of service
    """
    init_cmd(focus=focus, local=local)


@app.command(name="doctor", help="Check Pipelex configuration health and suggest fixes")
def doctor_command(
    fix: Annotated[bool, typer.Option("--fix", "-f", help="Offer to fix detected issues interactively")] = False,
) -> None:
    """Check Pipelex configuration health."""
    doctor_cmd(fix=fix)


@app.command(name="update", help="Update the model deck to match the installed pipelex version")
def update_command(
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            "-l",
            help="Force the project-local .pipelex/ deck. Default targets the resolved deck dir (project if .pipelex/ exists, else global)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Apply updates without the interactive confirmation prompt")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the planned actions without modifying any file")] = False,
    no_backup: Annotated[bool, typer.Option("--no-backup", help="Skip .bak files when overwriting locally-modified deck files")] = False,
) -> None:
    """Refresh the installed deck to match the kit shipped with the running pipelex version."""
    update_cmd(local=local, yes=yes, dry_run=dry_run, no_backup=no_backup)


app.add_typer(
    build_app, name="build", help="Generate AI methods from natural language requirements: pipelines in .mthds format and python code to run them"
)
app.add_typer(
    validate_app,
    name="validate",
    help="Validate a method or pipe: static validation for syntax and dependencies, dry-run execution for logic and consistency",
)
app.add_typer(run_app, name="run", help="Run a method or pipe, optionally providing a specific bundle file (.mthds)")
app.add_typer(graph_app, name="graph", help="Generate and render execution graphs")
app.add_typer(show_app, name="show", help="Show configuration, pipes, and list AI models")
app.command(name="which", help="Locate where a pipe is defined, similar to 'which' for executables")(which_cmd)
app.add_typer(plugins_app, name="plugins", help="Inspect the discovered plugins (inference backends, orchestrators) and their contributions")


def _config_for_cli_harvest() -> PipelexConfig:
    """Load config for the plugin-command harvest without side effects.

    Runs on every ``pipelex`` invocation (including ``--help`` / ``init``), so it must never create
    ``~/.pipelex/`` (``ensure_global_if_missing=False``) and must survive a broken user config — a
    malformed override must not brick the very commands (``init``/``doctor``) that fix it. On any load
    or validation failure it falls back to the shipped package defaults, which always validate.
    """
    try:
        config_dict = config_manager.load_config(ensure_global_if_missing=False)
        return PipelexConfig.model_validate(config_dict)
    except (TomlError, ValidationError) as exc:
        log.debug(f"Plugin CLI harvest: user config unreadable ({exc}); using package defaults.")
        return PipelexConfig.model_validate(config_manager.load_base_config_dict())


def _register_discovered_cli_commands() -> list[str]:
    """Harvest plugin-contributed CLI commands at CLI-build time (D3) and register them on ``app``.

    Runs the pure ``build_registrar`` once after loading config — the same function boot runs. D5's
    deferred slot-claim thunks mean this never constructs a host-runtime impl (no ``temporalio`` import)
    even when ``temporal.is_enabled``: only ``add_cli_command`` (import-light command callables) feeds
    the harvest. Returns the registered command names, in discovery order, for ``list_commands``.
    """
    registrar = build_registrar(config=_config_for_cli_harvest())
    names: list[str] = []
    for cli_command in registrar.cli_commands:
        module_path, _, attribute = cli_command.import_path.partition(":")
        command = getattr(importlib.import_module(module_path), attribute)
        app.command(name=cli_command.name, help=cli_command.help)(command)
        names.append(cli_command.name)
    return names


_PLUGIN_COMMAND_NAMES: list[str] = _register_discovered_cli_commands()
