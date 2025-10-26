import os
import shutil
from importlib.metadata import metadata

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from pipelex.exceptions import PipelexCLIError
from pipelex.kit.paths import get_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryMode
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from pipelex.types import StrEnum

PACKAGE_NAME = __name__.split(".", maxsplit=1)[0]
PACKAGE_VERSION = metadata(PACKAGE_NAME)["Version"]


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    CONFIG = "config"
    TELEMETRY = "telemetry"


def init_config(reset: bool = False, dry_run: bool = False) -> int:
    """Initialize pipelex configuration in the .pipelex directory. Does not install telemetry, just the main config dans inference backends.

    Args:
        reset: Whether to overwrite existing files.
        dry_run: Whether to only print the files that would be copied, without actually copying them.

    Returns:
        The number of files copied.
    """
    config_template_dir = str(get_configs_dir())
    target_config_dir = config_manager.pipelex_config_dir

    os.makedirs(target_config_dir, exist_ok=True)

    try:
        copied_files: list[str] = []
        existing_files: list[str] = []

        def copy_directory_structure(src_dir: str, dst_dir: str, relative_path: str = "", dry_run: bool = False) -> None:
            """Recursively copy directory structure, handling existing files."""
            for item in os.listdir(src_dir):
                src_item = os.path.join(src_dir, item)
                dst_item = os.path.join(dst_dir, item)
                relative_item = os.path.join(relative_path, item) if relative_path else item

                # Skip telemetry.toml - it will be created when user is prompted
                if item == TELEMETRY_CONFIG_FILE_NAME:
                    continue

                if os.path.isdir(src_item):
                    os.makedirs(dst_item, exist_ok=True)
                    copy_directory_structure(src_item, dst_item, relative_item)
                elif os.path.exists(dst_item) and not reset:
                    existing_files.append(relative_item)
                else:
                    shutil.copy2(src_item, dst_item)
                    if not dry_run:
                        copied_files.append(relative_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=target_config_dir, dry_run=dry_run)

        if dry_run:
            return len(copied_files)

        # Report results
        if copied_files:
            typer.echo(f"✅ Copied {len(copied_files)} files to {target_config_dir}:")
            for file in sorted(copied_files):
                typer.echo(f"   • {file}")

        if existing_files:
            typer.echo(f"ℹ️  Skipped {len(existing_files)} existing files (use --reset to overwrite):")
            for file in sorted(existing_files):
                typer.echo(f"   • {file}")

        if not copied_files and not existing_files:
            typer.echo(f"✅ Configuration directory {target_config_dir} is already up to date")

    except Exception as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    reset: bool = False,
) -> TelemetryMode | None:
    """Initialize Pipelex configuration and telemetry if needed, in a unified flow.

    Args:
        focus: What to initialize - 'config', 'telemetry', or 'all' (default)
        reset: Whether to reset/overwrite existing files
    """
    console = Console()
    pipelex_config_dir = config_manager.pipelex_config_dir
    telemetry_config_path = os.path.join(pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME)

    # Determine what to check based on focus parameter
    check_config = focus in (InitFocus.ALL, InitFocus.CONFIG)
    check_telemetry = focus in (InitFocus.ALL, InitFocus.TELEMETRY)

    # Check what needs to be initialized
    nb_missing_config_files = init_config(reset=False, dry_run=True) if check_config else 0
    needs_config = check_config and (nb_missing_config_files > 0 or reset)
    needs_telemetry = check_telemetry and (not path_exists(telemetry_config_path) or reset)

    # Track if user already confirmed to avoid double prompting
    user_already_confirmed = False

    # If nothing needs to be done, handle based on focus
    if not needs_config and not needs_telemetry:
        match focus:
            case InitFocus.TELEMETRY:
                # Special case: if user explicitly asked for telemetry, offer to reconfigure
                console.print()
                console.print("[green]✓[/green] Telemetry preferences are already configured!")
                console.print()
                console.print(f"[dim]Configuration file:[/dim] [cyan]{telemetry_config_path}[/cyan]")
                console.print()

                if Confirm.ask("[bold]Would you like to reconfigure telemetry preferences?[/bold]", default=False):
                    # User wants to reconfigure, so proceed with telemetry setup
                    needs_telemetry = True
                    user_already_confirmed = True
                else:
                    console.print("\n[dim]No changes made.[/dim]")
                    console.print()
                    return None

            case InitFocus.ALL:
                console.print()
                console.print("[green]✓[/green] Pipelex is already fully initialized!")
                console.print()
                console.print("[dim]Configuration files are in place:[/dim] [cyan].pipelex/[/cyan]")
                console.print("[dim]Telemetry preferences are configured[/dim]")
                console.print()
                console.print("[dim]💡 Tip: Use[/dim] [cyan]--reset[/cyan] [dim]to reconfigure or troubleshoot:[/dim]")
                console.print("   [cyan]pipelex init --reset[/cyan]")
                console.print()
                return None

            case InitFocus.CONFIG:
                console.print()
                console.print("[green]✓[/green] Configuration files are already in place!")
                console.print()
                console.print("[dim]Configuration directory:[/dim] [cyan].pipelex/[/cyan]")
                console.print()
                console.print("[dim]💡 Tip: Use[/dim] [cyan]--reset[/cyan] [dim]to reconfigure or troubleshoot:[/dim]")
                console.print(f"   [cyan]pipelex init {focus} --reset[/cyan]")
                console.print()
                return None

    try:
        # Show unified initialization prompt (skip if user already confirmed)
        if not user_already_confirmed:
            console.print()

            # Build message based on what's being initialized
            message_parts: list[str] = []
            if reset:
                if needs_config and needs_telemetry:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] configuration files in [cyan].pipelex/[/cyan]")
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] telemetry preferences")
                elif needs_config:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] configuration files in [cyan].pipelex/[/cyan]")
                elif needs_telemetry:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] telemetry preferences")
            elif needs_config and needs_telemetry:
                message_parts.append("• Create required configuration files in [cyan].pipelex/[/cyan]")
                message_parts.append("• Ask you to choose your telemetry preferences")
            elif needs_config:
                message_parts.append("• Create required configuration files in [cyan].pipelex/[/cyan]")
            elif needs_telemetry:
                message_parts.append("• Ask you to choose your telemetry preferences")

            if needs_config and needs_telemetry:
                title_text = "[bold yellow]Resetting Configuration[/bold yellow]" if reset else "[bold cyan]Pipelex Initialization[/bold cyan]"
            elif needs_config:
                title_text = "[bold yellow]Resetting Configuration Files[/bold yellow]" if reset else "[bold cyan]Configuration Setup[/bold cyan]"
            else:
                title_text = "[bold yellow]Resetting Telemetry[/bold yellow]" if reset else "[bold cyan]Telemetry Setup[/bold cyan]"

            message = "\n".join(message_parts)
            border_color = "yellow" if reset else "cyan"

            panel = Panel(
                message,
                title=title_text,
                border_style=border_color,
                padding=(1, 2),
            )
            console.print(panel)

            if not Confirm.ask("[bold]Continue with initialization?[/bold]", default=True):
                console.print("\n[yellow]Initialization cancelled.[/yellow]")
                if needs_config:
                    match focus:
                        case InitFocus.ALL:
                            init_cmd_str = "pipelex init"
                        case InitFocus.CONFIG:
                            init_cmd_str = f"pipelex init {focus}"
                        case InitFocus.TELEMETRY:
                            init_cmd_str = f"pipelex init {focus}"
                    console.print(f"[dim]You can initialize later by running:[/dim] [cyan]{init_cmd_str}[/cyan]")
                console.print()
                raise typer.Exit(code=0)
        else:
            # User already confirmed, just add a blank line for spacing
            console.print()

        # Step 1: Initialize config if needed
        if needs_config:
            console.print()
            init_config(reset=reset)

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
