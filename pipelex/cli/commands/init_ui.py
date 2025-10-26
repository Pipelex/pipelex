"""UI components for the init command.

This module contains all user interface logic for the Pipelex initialization process,
including prompts, panels, and user input validation.
"""

from __future__ import annotations

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from pipelex.system.telemetry.telemetry_config import TelemetryMode
from pipelex.types import StrEnum

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


def build_backend_selection_panel() -> Panel:
    """Create a Rich Panel for backend selection with options table.

    Returns:
        A Panel containing the backend selection interface.
    """
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

    return Panel(
        Group(description, Text(""), table),
        title="[bold yellow]Inference Backend Selection[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_backend_indices(console: Console) -> list[int]:
    """Prompt user to select backend indices with validation.

    Args:
        console: Rich Console instance for user interaction.

    Returns:
        List of validated backend indices selected by the user.
    """
    selected_indices: list[int] = []
    while True:
        choice_str = Prompt.ask("[bold]Enter your choices[/bold]", default="0", console=console)
        choice_input = choice_str.strip()

        # Parse input - handle empty, comma-separated, and space-separated
        if not choice_input or choice_input == "0":
            # Default: only pipelex_inference
            selected_indices = [0]
            break

        # Split by comma or space
        parts = choice_input.replace(",", " ").split()

        try:
            indices = [int(part.strip()) for part in parts if part.strip()]

            # Validate all indices are in range
            invalid_indices = [i for i in indices if i < 0 or i >= len(BACKEND_OPTIONS)]
            if invalid_indices:
                console.print(f"[red]Invalid choice(s): {invalid_indices}.[/red] Please enter numbers between 0 and {len(BACKEND_OPTIONS) - 1}.\n")
                continue

            selected_indices = indices
            break

        except ValueError:
            console.print(f"[red]Invalid input: '{choice_str}'.[/red] Please enter numbers separated by commas or spaces.\n")

    return selected_indices


def display_selected_backends(console: Console, selected_indices: list[int]) -> None:
    """Display confirmation of selected backends.

    Args:
        console: Rich Console instance for output.
        selected_indices: List of selected backend indices.
    """
    selected_names = [BACKEND_OPTIONS[idx][1] for idx in sorted(selected_indices)]
    console.print(f"\n[green]✓[/green] Configured {len(selected_names)} backend(s):")
    for name in selected_names:
        console.print(f"   • {name}")


def build_telemetry_selection_panel() -> Panel:
    """Create a Rich Panel for telemetry mode selection.

    Returns:
        A Panel containing the telemetry selection interface.
    """
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

    return Panel(
        Group(description, Text(""), table),
        title="[bold yellow]Telemetry Configuration[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_telemetry_mode(console: Console) -> TelemetryMode:
    """Prompt user to select telemetry mode with validation.

    Args:
        console: Rich Console instance for user interaction.

    Returns:
        Selected TelemetryMode.

    Raises:
        typer.Exit: If user chooses to quit.
    """
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
    telemetry_mode: TelemetryMode | None = None
    while telemetry_mode is None:
        choice_str = Prompt.ask("[bold]Enter your choice[/bold]", console=console)
        choice_input = choice_str.lower().strip()

        # Handle quit option
        if choice_input in ("q", "quit"):
            console.print("\n[yellow]Exiting without configuring telemetry.[/yellow]")
            raise typer.Exit(code=0)

        if choice_input in mode_map:
            telemetry_mode = mode_map[choice_input]
        else:
            console.print(
                f"[red]Invalid choice: '{choice_str}'.[/red] "
                "Please enter [cyan]1[/cyan], [cyan]2[/cyan], [cyan]3[/cyan], or [cyan]q[/cyan] to quit.\n"
            )

    return telemetry_mode


def display_already_configured_message(focus: InitFocus, console: Console, config_path: str) -> bool:
    """Display 'already configured' message and ask if user wants to reconfigure.

    Args:
        focus: The initialization focus area.
        console: Rich Console instance for output.
        config_path: Path to the configuration file.

    Returns:
        True if user wants to reconfigure, False otherwise.
    """
    # Mapping of focus to (subject, action_verb)
    focus_messages = {
        InitFocus.INFERENCE: ("Inference backends", "inference backends"),
        InitFocus.TELEMETRY: ("Telemetry preferences", "telemetry preferences"),
        InitFocus.CONFIG: ("Configuration files", "configuration"),
    }

    if focus == InitFocus.ALL:
        console.print()
        console.print("[green]✓[/green] Pipelex is already fully initialized!")
        console.print()
        console.print("[dim]Configuration files are in place:[/dim] [cyan].pipelex/[/cyan]")
        console.print("[dim]Telemetry preferences are configured[/dim]")
        console.print()
        console.print("[dim]💡 Tip: Use[/dim] [cyan]--reset[/cyan] [dim]to reconfigure or troubleshoot:[/dim]")
        console.print("   [cyan]pipelex init --reset[/cyan]")
        console.print()
        return False

    if focus == InitFocus.CONFIG:
        console.print()
        console.print("[green]✓[/green] Configuration files are already in place!")
        console.print()
        console.print("[dim]Configuration directory:[/dim] [cyan].pipelex/[/cyan]")
        console.print()
        console.print("[dim]💡 Tip: Use[/dim] [cyan]--reset[/cyan] [dim]to reconfigure or troubleshoot:[/dim]")
        console.print(f"   [cyan]pipelex init {focus} --reset[/cyan]")
        console.print()
        return False

    if focus in focus_messages:
        subject, action_verb = focus_messages[focus]
        console.print()
        console.print(f"[green]✓[/green] {subject} are already configured!")
        console.print()
        console.print(f"[dim]Configuration file:[/dim] [cyan]{config_path}[/cyan]")
        console.print()

        return Confirm.ask(f"[bold]Would you like to reconfigure {action_verb}?[/bold]", default=False)

    return False


def build_initialization_panel(needs_config: bool, needs_inference: bool, needs_telemetry: bool, reset: bool) -> Panel:
    """Build the initialization confirmation panel.

    Args:
        needs_config: Whether config initialization is needed.
        needs_inference: Whether inference setup is needed.
        needs_telemetry: Whether telemetry setup is needed.
        reset: Whether this is a reset operation.

    Returns:
        A Panel containing the initialization confirmation message.
    """
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

    return Panel(
        message,
        title=title_text,
        border_style=border_color,
        padding=(1, 2),
    )
