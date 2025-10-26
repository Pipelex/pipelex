from typing import Annotated

import typer
from click import Command, Context
from rich.console import Console
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.build_cmd import build_app
from pipelex.cli.commands.init_cmd import InitFocus, init_cmd
from pipelex.cli.commands.kit_cmd import kit_app
from pipelex.cli.commands.run_cmd import run_cmd
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.validate_cmd import validate_cmd
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class PipelexCLI(TyperGroup):
    @override
    def list_commands(self, ctx: Context) -> list[str]:
        # List the commands in the proper order because natural ordering doesn't work between Typer groups and commands
        return ["init", "kit", "build", "validate", "run", "show"]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


@app.callback(invoke_without_command=True)
def app_callback(ctx: typer.Context) -> None:
    """Run pre-command checks like printing the logo and checking telemetry consent."""
    console = Console()
    console.print(
        """

░█████████  ░[bold green4]██[/bold green4]                      ░██
░██     ░██                          ░██
░██     ░██ ░██░████████   ░███████  ░██  ░███████  ░██    ░[bold green4]██[/bold green4]
░█████████  ░██░██    ░██ ░██    ░██ ░██ ░██    ░██  ░██  ░██
░██         ░██░██    ░██ ░█████████ ░██ ░█████████   ░█████
░██         ░██░███   ░██ ░██        ░██ ░██         ░██  ░██
░██         ░██░██░█████   ░███████  ░██  ░███████  ░██    ░██
               ░██
               ░██

"""
    )
    # Skip checks if no command is being run (e.g., just --help) or if running init command
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand == "init":
        return

    TelemetryManagerAbstract.telemetry_mode_just_set = init_cmd()


@app.command(name="init", help="Initialize Pipelex configuration in a `.pipelex` directory")
def init_command(
    focus: Annotated[InitFocus, typer.Argument(help="What to initialize: 'config', 'telemetry', or 'all'")] = InitFocus.ALL,
    reset: Annotated[bool, typer.Option("--reset", "-r", help="Reset existing configuration files")] = False,
) -> None:
    """Initialize Pipelex configuration and telemetry."""
    init_cmd(focus=focus, reset=reset)


app.add_typer(kit_app, name="kit", help="Manage kit assets: agent rules, migration rules")
app.add_typer(
    build_app, name="build", help="Generate AI workflows from natural language requirements: pipelines in .plx format and python code to run them"
)
app.command(name="validate", help="Validate pipes: static validation for syntax and dependencies, dry-run execution for logic and consistency")(
    validate_cmd
)
app.command(name="run", help="Run a pipe, optionally providing a specific bundle file (.plx)")(run_cmd)
app.add_typer(show_app, name="show", help="Show configuration, pipes, and list AI models")
