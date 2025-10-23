import os

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.build_cmd import build_app
from pipelex.cli.commands.init_cmd import init_app
from pipelex.cli.commands.kit_cmd import kit_app
from pipelex.cli.commands.run_cmd import run_cmd
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.validate_cmd import validate_cmd
from pipelex.hub import get_telemetry_config
from pipelex.system.configuration.config_loader import config_manager
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


def check_telemetry_consent() -> None:
    """Check if user has customized telemetry settings and prompt if not."""
    # Check if .pipelex directory exists - if not, user must run pipelex init first
    pipelex_config_dir = config_manager.pipelex_config_dir
    if not path_exists(pipelex_config_dir):
        typer.echo("Pipelex has not been initialized in this directory.", err=True)
        typer.echo("Please run 'pipelex init' first to set up the configuration.", err=True)
        raise typer.Exit(code=1)

    telemetry_config_path = os.path.join(pipelex_config_dir, "telemetry.toml")
    if not path_exists(telemetry_config_path):
        typer.echo(f"Telemetry configuration file not found at {telemetry_config_path}", err=True)
        typer.echo("Please run 'pipelex init' to restore the configuration.", err=True)
        raise typer.Exit(code=1)

    # Load the TOML file with tomlkit to preserve formatting and comments
    toml_doc = load_toml_with_tomlkit(telemetry_config_path)

    try:
        # Check if settings have already been customized
        if toml_doc["settings_customized"]:
            return

        # Prompt user for telemetry preference
        typer.echo("\n" + "=" * 70)
        typer.echo("Telemetry Configuration")
        typer.echo("=" * 70)
        typer.echo("\nPipelex can collect anonymous usage data to help improve the product.")
        typer.echo("\nPlease choose your telemetry preference:")
        typer.echo("  [1] off        - No telemetry data collected")
        typer.echo("  [2] anonymous  - Anonymous usage data only (default)")
        typer.echo("  [3] identified - Usage data with user identification")
        typer.echo()

        choice = typer.prompt(
            "Enter your choice",
            type=int,
            default=2,
            show_default=True,
        )

        # Validate choice
        if choice not in [1, 2, 3]:
            typer.echo(f"Invalid choice: {choice}. Defaulting to anonymous.")
            choice = 2

        # Map choice to telemetry mode
        mode_map = {
            1: "off",
            2: "anonymous",
            3: "identified",
        }
        telemetry_mode = mode_map[choice]

        # Update the settings
        toml_doc["settings_customized"] = True
        toml_doc["telemetry_mode"] = telemetry_mode

        # Save back to file
        save_toml_to_path(toml_doc, telemetry_config_path)

        typer.echo(f"\n✓ Telemetry mode set to: {telemetry_mode}")
        typer.echo("=" * 70 + "\n")

    except Exception as e:
        # Silently fail if there's any issue - don't block CLI usage
        typer.echo(f"Warning: Could not save telemetry preference: {e}", err=True)


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
    """Run pre-command checks like telemetry consent."""
    # Skip checks if no command is being run (e.g., just --help) or if running init command
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand == "init":
        return

    check_telemetry_consent()


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
