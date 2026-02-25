from typing import Annotated

import click
import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.build.app import build_app
from pipelex.cli.commands.doctor_cmd import doctor_cmd
from pipelex.cli.commands.graph_cmd import graph_app
from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.run.app import run_app
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.validate.app import validate_app
from pipelex.cli.commands.which_cmd import which_cmd
from pipelex.cli.readiness import check_readiness
from pipelex.hub import get_console
from pipelex.tools.misc.package_utils import get_package_version


class PipelexCLI(TyperGroup):
    """Custom CLI group that handles global options like --no-logo."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        # List the commands in the proper order because natural ordering doesn't work between Typer groups and commands
        return ["init", "doctor", "build", "validate", "run", "graph", "show", "which"]

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
        """Intercept --no-logo from args before Click/Typer processes them.

        This allows --no-logo to be placed anywhere in the command line
        (before or after subcommands) while keeping the CLI architecture clean.
        """
        no_logo = "--no-logo" in args
        if no_logo:
            args = [arg for arg in args if arg != "--no-logo"]

        ctx = super().make_context(info_name, args, parent, **extra)
        ctx.ensure_object(dict)
        ctx.obj["no_logo"] = no_logo
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

    # Get no_logo flag from context (set by PipelexCLI.make_context)
    click_ctx = click.get_current_context()
    no_logo = click_ctx.obj.get("no_logo", False) if click_ctx.obj else False

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
    # Skip checks if no command is being run (e.g., just --help) or if running init/doctor command
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand in {"init", "doctor"}:
        return

    # Check system readiness (dependencies and venv for dev installs)
    check_readiness()


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
