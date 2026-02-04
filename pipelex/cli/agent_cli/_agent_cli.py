"""Main entry point for the agent CLI."""

from typing import Annotated

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.doctor_cmd import doctor_cmd
from pipelex.tools.misc.package_utils import get_package_version


class PipelexAgentCLI(TyperGroup):
    """Custom Typer group for pipelex-agent CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return ["doctor"]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexAgentCLI,
)


def version_callback(value: bool) -> None:
    """Print version and exit when --version is passed."""
    if value:
        package_version = get_package_version()
        typer.echo(f"pipelex-agent {package_version}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    version: Annotated[
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
    """Agent CLI callback - no logo, minimal output."""
    # No logo, no banner - agent CLI is silent by default


@app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")
def doctor_command() -> None:
    """Check Pipelex configuration health with auto-fix enabled."""
    doctor_cmd(fix=True)
