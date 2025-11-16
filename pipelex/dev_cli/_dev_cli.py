"""Main entry point for the internal development CLI."""

from typing import Annotated

import typer
from click import Command, Context
from rich.console import Console
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.dev_cli.commands.check_config_sync_cmd import LeadingConfig, check_config_sync_cmd
from pipelex.tools.misc.package_utils import get_package_version


class PipelexDevCLI(TyperGroup):
    """Custom Typer group for pipelex-dev CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return ["check-config-sync"]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


def main() -> None:
    """Entry point for the pipelex-dev CLI."""
    app()


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexDevCLI,
)


@app.callback(invoke_without_command=True)
def app_callback(_ctx: typer.Context) -> None:
    console = Console()
    package_version = get_package_version()
    console.print(
        f"""
[bold cyan]Pipelex Dev CLI[/bold cyan] [dim]v{package_version}[/dim]

[yellow]⚠️  Internal Development Tools Only[/yellow]
[dim]This CLI is for Pipelex development and is not distributed with the package.[/dim]
"""
    )


@app.command(name="check-config-sync", help="Verify that .pipelex and pipelex/kit/configs are in sync")
def check_config_sync_command(
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show differences if found")] = True,
    leading: Annotated[
        LeadingConfig,
        typer.Option(help="Which configuration is the leading (left) one: 'installed' (.pipelex) or 'kit' (pipelex/kit/configs)"),
    ] = LeadingConfig.INSTALLED,
) -> None:
    """Verify that .pipelex and pipelex/kit/configs are in sync."""
    check_config_sync_cmd(show_diff=show_diff, leading=leading)
