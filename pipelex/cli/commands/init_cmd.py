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
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from pipelex.types import StrEnum

PACKAGE_NAME = __name__.split(".", maxsplit=1)[0]
PACKAGE_VERSION = metadata(PACKAGE_NAME)["Version"]

# Backend definitions for interactive selection
BACKEND_OPTIONS = [
    ("pipelex_inference", "⭐ Pipelex Inference", "Unified access to all providers (Recommended)"),
    ("azure_openai", "Azure OpenAI", "Azure OpenAI Service"),
    ("bedrock", "AWS Bedrock", "AWS Bedrock"),
    ("google", "Google AI", "Google AI"),
    ("vertexai", "Google Vertex AI", "Google Vertex AI"),
    ("openai", "OpenAI", "OpenAI"),
    ("anthropic", "Anthropic", "Anthropic"),
    ("mistral", "Mistral AI", "Mistral AI"),
    ("xai", "xAI", "xAI"),
    ("ollama", "Ollama", "Ollama (local)"),
    ("blackboxai", "BlackBox AI", "BlackBox AI"),
    ("fal", "FAL", "FAL (image generation)"),
]


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    CONFIG = "config"
    INFERENCE = "inference"
    TELEMETRY = "telemetry"


def customize_backends_config() -> None:
    """Interactively customize which inference backends are enabled in backends.toml."""
    console = Console()
    backends_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "backends.toml")

    if not path_exists(backends_toml_path):
        console.print("[yellow]⚠ Warning: backends.toml not found, skipping backend customization[/yellow]")
        return

    try:
        # Load the backends.toml file
        toml_doc = load_toml_with_tomlkit(backends_toml_path)

        console.print()

        # Create table for backend options
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan", justify="right", width=4)
        table.add_column(style="bold", width=25)
        table.add_column(style="dim")

        for idx, (_, backend_name, backend_desc) in enumerate(BACKEND_OPTIONS):
            table.add_row(f"[{idx}]", backend_name, backend_desc)

        description = Text(
            "Select which inference backends you have access to.\n"
            "Enter numbers separated by commas or spaces (e.g., '0,5,6' or '0 5 6').\n"
            "Press Enter for the recommended default.",
            style="dim",
        )

        panel = Panel(
            Group(description, Text(""), table),
            title="[bold yellow]Inference Backend Selection[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
        console.print(panel)

        # Get user input with validation loop
        selected_indices: list[int] = []
        while True:
            choice_str = Prompt.ask("[bold]Enter your choices[/bold]", default="0", console=console)
            choice_normalized = choice_str.strip()

            # Parse input - handle empty, comma-separated, and space-separated
            if not choice_normalized or choice_normalized == "0":
                # Default: only pipelex_inference
                selected_indices = [0]
                break

            # Split by comma or space
            parts = choice_normalized.replace(",", " ").split()

            try:
                indices = [int(part.strip()) for part in parts if part.strip()]

                # Validate all indices are in range
                invalid_indices = [i for i in indices if i < 0 or i >= len(BACKEND_OPTIONS)]
                if invalid_indices:
                    console.print(
                        f"[red]Invalid choice(s): {invalid_indices}.[/red] Please enter numbers between 0 and {len(BACKEND_OPTIONS) - 1}.\n"
                    )
                    continue

                selected_indices = indices
                break

            except ValueError:
                console.print(f"[red]Invalid input: '{choice_str}'.[/red] Please enter numbers separated by commas or spaces.\n")

        # Update backends.toml based on selections
        selected_backend_keys = {BACKEND_OPTIONS[idx][0] for idx in selected_indices}

        for backend_key, _, _ in BACKEND_OPTIONS:
            if backend_key in toml_doc:
                backend_section = toml_doc[backend_key]
                # Set enabled field based on selection (works with tomlkit's special types)
                backend_section["enabled"] = backend_key in selected_backend_keys  # type: ignore[index]

        # Save the modified file
        save_toml_to_path(toml_doc, backends_toml_path)

        # Display selected backends
        selected_names = [BACKEND_OPTIONS[idx][1] for idx in sorted(selected_indices)]
        console.print(f"\n[green]✓[/green] Configured {len(selected_names)} backend(s):")
        for name in selected_names:
            console.print(f"   • {name}")

    except Exception as exc:
        console.print(f"[yellow]⚠ Warning: Failed to customize backends: {exc}[/yellow]")
        console.print("[dim]You can manually edit .pipelex/inference/backends.toml later[/dim]")


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
                    if not dry_run:
                        os.makedirs(dst_item, exist_ok=True)
                    copy_directory_structure(src_item, dst_item, relative_item, dry_run)
                elif os.path.exists(dst_item) and not reset:
                    existing_files.append(relative_item)
                else:
                    if not dry_run:
                        shutil.copy2(src_item, dst_item)
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
):
    """Initialize Pipelex configuration, inference backends, and telemetry if needed, in a unified flow.

    Args:
        focus: What to initialize - 'config', 'inference', 'telemetry', or 'all' (default)
        reset: Whether to reset/overwrite existing files
    """
    console = Console()
    pipelex_config_dir = config_manager.pipelex_config_dir
    telemetry_config_path = os.path.join(pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME)
    backends_toml_path = os.path.join(pipelex_config_dir, "inference", "backends.toml")

    # Determine what to check based on focus parameter
    check_config = focus in (InitFocus.ALL, InitFocus.CONFIG)
    check_inference = focus in (InitFocus.ALL, InitFocus.INFERENCE)
    check_telemetry = focus in (InitFocus.ALL, InitFocus.TELEMETRY)

    # Check what needs to be initialized
    nb_missing_config_files = init_config(reset=False, dry_run=True) if check_config else 0
    needs_config = check_config and (nb_missing_config_files > 0 or reset)
    needs_inference = check_inference and (not path_exists(backends_toml_path) or reset)
    needs_telemetry = check_telemetry and (not path_exists(telemetry_config_path) or reset)

    # Track if user already confirmed to avoid double prompting
    user_already_confirmed = False

    # If nothing needs to be done, handle based on focus
    if not needs_config and not needs_inference and not needs_telemetry:
        match focus:
            case InitFocus.INFERENCE:
                # Special case: if user explicitly asked for inference, offer to reconfigure
                console.print()
                console.print("[green]✓[/green] Inference backends are already configured!")
                console.print()
                console.print(f"[dim]Configuration file:[/dim] [cyan]{backends_toml_path}[/cyan]")
                console.print()

                if Confirm.ask("[bold]Would you like to reconfigure inference backends?[/bold]", default=False):
                    # User wants to reconfigure, so proceed with inference setup
                    needs_inference = True
                    user_already_confirmed = True
                else:
                    console.print("\n[dim]No changes made.[/dim]")
                    console.print()
                    return

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
                    return

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
                return

            case InitFocus.CONFIG:
                console.print()
                console.print("[green]✓[/green] Configuration files are already in place!")
                console.print()
                console.print("[dim]Configuration directory:[/dim] [cyan].pipelex/[/cyan]")
                console.print()
                console.print("[dim]💡 Tip: Use[/dim] [cyan]--reset[/cyan] [dim]to reconfigure or troubleshoot:[/dim]")
                console.print(f"   [cyan]pipelex init {focus} --reset[/cyan]")
                console.print()
                return

    try:
        # Show unified initialization prompt (skip if user already confirmed)
        if not user_already_confirmed:
            console.print()

            # Build message based on what's being initialized
            message_parts: list[str] = []
            if reset:
                if needs_config:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] configuration files in [cyan].pipelex/[/cyan]")
                if needs_inference:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] inference backends")
                if needs_telemetry:
                    message_parts.append("• [yellow]Reset and reconfigure[/yellow] telemetry preferences")
            else:
                if needs_config:
                    message_parts.append("• Create required configuration files in [cyan].pipelex/[/cyan]")
                if needs_inference:
                    message_parts.append("• Ask you to choose your inference backends")
                if needs_telemetry:
                    message_parts.append("• Ask you to choose your telemetry preferences")

            # Determine title based on what's being initialized
            num_items = sum([needs_config, needs_inference, needs_telemetry])
            if reset:
                if num_items > 1:
                    title_text = "[bold yellow]Resetting Configuration[/bold yellow]"
                elif needs_config:
                    title_text = "[bold yellow]Resetting Configuration Files[/bold yellow]"
                elif needs_inference:
                    title_text = "[bold yellow]Resetting Inference Backends[/bold yellow]"
                else:
                    title_text = "[bold yellow]Resetting Telemetry[/bold yellow]"
            elif num_items > 1:
                title_text = "[bold cyan]Pipelex Initialization[/bold cyan]"
            elif needs_config:
                title_text = "[bold cyan]Configuration Setup[/bold cyan]"
            elif needs_inference:
                title_text = "[bold cyan]Inference Backend Setup[/bold cyan]"
            else:
                title_text = "[bold cyan]Telemetry Setup[/bold cyan]"

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
                if needs_config or needs_inference or needs_telemetry:
                    match focus:
                        case InitFocus.ALL:
                            init_cmd_str = "pipelex init"
                        case InitFocus.CONFIG | InitFocus.INFERENCE | InitFocus.TELEMETRY:
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
            # If we just initialized config and focus includes inference, enable inference setup
            if check_inference and path_exists(backends_toml_path):
                needs_inference = True

        # Step 2: Set up inference backends if needed
        if needs_inference:
            console.print()
            customize_backends_config()

        # Step 3: Set up telemetry if needed
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
        TelemetryManagerAbstract.telemetry_mode_just_set = telemetry_mode

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:
        console.print(f"\n[red]⚠ Warning: Initialization failed: {exc}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
