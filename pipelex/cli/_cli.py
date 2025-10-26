import os

import typer
from click import Command, Context
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.build_cmd import build_app
from pipelex.cli.commands.init_cmd import do_init_config, init_app
from pipelex.cli.commands.kit_cmd import kit_app
from pipelex.cli.commands.run_cmd import run_cmd
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.validate_cmd import validate_cmd
from pipelex.kit.paths import get_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


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


def initialize_pipelex_if_needed() -> TelemetryMode | None:
    """Initialize Pipelex configuration and telemetry if needed, in a unified flow."""
    console = Console()
    pipelex_config_dir = config_manager.pipelex_config_dir
    telemetry_config_path = os.path.join(pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME)

    # Check what needs to be initialized
    needs_config = not path_exists(pipelex_config_dir)
    needs_telemetry = not path_exists(telemetry_config_path)

    # If both are already set up, nothing to do
    if not needs_config and not needs_telemetry:
        return None

    try:
        # Show unified initialization prompt
        console.print()
        if needs_config and needs_telemetry:
            message = (
                "Pipelex needs to be initialized. This will:\n\n"
                "• Create configuration files in [cyan].pipelex/[/cyan]\n"
                "• Ask you to choose your telemetry preferences"
            )
        elif needs_config:
            message = "Pipelex configuration not found. This will:\n\n• Create configuration files in [cyan].pipelex/[/cyan]"
        else:  # needs_telemetry only
            message = "Telemetry preferences need to be configured."

        panel = Panel(
            message,
            title="[bold cyan]Pipelex Initialization[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(panel)

        if not Confirm.ask("[bold]Continue with initialization?[/bold]", default=True):
            console.print("\n[yellow]Initialization cancelled.[/yellow]")
            if needs_config:
                console.print("[dim]You can initialize later by running:[/dim] [cyan]pipelex init config[/cyan]")
            console.print()
            raise typer.Exit(code=0)

        # Step 1: Initialize config if needed
        if needs_config:
            console.print()
            do_init_config(reset=False)

        # Step 2: Set up telemetry if needed
        telemetry_mode: TelemetryMode | None = None
        if needs_telemetry:
            console.print()

            # Create a table for telemetry options
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column(style="bold cyan", justify="right")
            table.add_column(style="bold")
            table.add_column()

            table.add_row("[1]", TelemetryMode.OFF, "No telemetry data collected")
            table.add_row("[2]", TelemetryMode.ANONYMOUS, "Anonymous usage data only")
            table.add_row("[3]", TelemetryMode.IDENTIFIED, "Usage data with user identification")
            table.add_row("[Q]", "[dim]quit[/dim]", "[dim]Exit without configuring[/dim]")

            description = Text(
                "Pipelex can collect anonymous usage data to help improve the product.",
                style="dim",
            )
            telemetry_panel = Panel(
                Group(description, Text(""), table),
                title="[bold yellow]Telemetry Configuration[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
            console.print(telemetry_panel)

            # Map choice to telemetry mode
            mode_map: dict[str, TelemetryMode] = {
                "1": TelemetryMode.OFF,
                "2": TelemetryMode.ANONYMOUS,
                "3": TelemetryMode.IDENTIFIED,
                "off": TelemetryMode.OFF,
                "anonymous": TelemetryMode.ANONYMOUS,
                "identified": TelemetryMode.IDENTIFIED,
            }

            # Loop until valid input
            while telemetry_mode is None:
                choice_str = Prompt.ask("[bold]Enter your choice[/bold]", console=console)
                choice_normalized = choice_str.lower().strip()

                # Handle quit option
                if choice_normalized in ("q", "quit"):
                    console.print("\n[yellow]Exiting without configuring telemetry.[/yellow]")
                    raise typer.Exit(code=0)

                if choice_normalized in mode_map:
                    telemetry_mode = mode_map[choice_normalized]
                else:
                    console.print(
                        f"[red]Invalid choice: '{choice_str}'.[/red] "
                        "Please enter [cyan]1[/cyan], [cyan]2[/cyan], [cyan]3[/cyan], or [cyan]q[/cyan] to quit.\n"
                    )

            # Save telemetry config
            template_path = os.path.join(str(get_configs_dir()), TELEMETRY_CONFIG_FILE_NAME)
            toml_doc = load_toml_with_tomlkit(template_path)
            toml_doc["telemetry_mode"] = telemetry_mode
            save_toml_to_path(toml_doc, telemetry_config_path)

            console.print(f"\n[green]✓[/green] Telemetry mode set to: [bold cyan]{telemetry_mode}[/bold cyan]")

        console.print()
        return telemetry_mode

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:
        console.print(f"\n[red]⚠ Warning: Initialization failed: {exc}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return None


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

    TelemetryManagerAbstract.telemetry_mode_just_set = initialize_pipelex_if_needed()


app.add_typer(init_app, name="init", help="Initialize Pipelex configuration in a `.pipelex` directory")
app.add_typer(kit_app, name="kit", help="Manage kit assets: agent rules, migration rules")
app.add_typer(
    build_app, name="build", help="Generate AI workflows from natural language requirements: pipelines in .plx format and python code to run them"
)
app.command(name="validate", help="Validate pipes: static validation for syntax and dependencies, dry-run execution for logic and consistency")(
    validate_cmd
)
app.command(name="run", help="Run a pipe, optionally providing a specific bundle file (.plx)")(run_cmd)
app.add_typer(show_app, name="show", help="Show configuration, pipes, and list AI models")
