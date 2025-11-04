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
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.types import StrEnum


def get_backend_options_from_toml(template_path: str, existing_path: str | None = None) -> list[tuple[str, str]]:
    """Get backend options dynamically from TOML files.

    Args:
        template_path: Path to the template backends.toml file.
        existing_path: Optional path to existing user backends.toml file.

    Returns:
        List of tuples (backend_key, display_name).
    """
    backend_options: list[tuple[str, str]] = []
    seen_backends: set[str] = set()

    # Read template backends
    if path_exists(template_path):
        toml_doc = load_toml_from_path(template_path)
        for backend_key in toml_doc:
            if backend_key != "internal":  # Skip internal backend
                backend_section = toml_doc[backend_key]
                # Try to get display_name from TOML, fallback to converted snake_case
                if isinstance(backend_section, dict) and "display_name" in backend_section:
                    display_name = str(backend_section["display_name"])  # type: ignore[arg-type]
                else:
                    display_name = snake_to_capitalize_first_letter(backend_key)
                backend_options.append((backend_key, display_name))
                seen_backends.add(backend_key)

    # Add any additional backends from existing config (custom backends user may have added)
    if existing_path and path_exists(existing_path):
        toml_doc = load_toml_from_path(existing_path)
        for backend_key in toml_doc:
            if backend_key != "internal" and backend_key not in seen_backends:
                backend_section = toml_doc[backend_key]
                # Try to get display_name from TOML, fallback to converted snake_case
                if isinstance(backend_section, dict) and "display_name" in backend_section:
                    display_name = str(backend_section["display_name"])  # type: ignore[arg-type]
                else:
                    display_name = snake_to_capitalize_first_letter(backend_key)
                backend_options.append((backend_key, display_name))
                seen_backends.add(backend_key)

    return backend_options


def get_currently_enabled_backends(backends_toml_path: str, backend_options: list[tuple[str, str]]) -> list[int]:
    """Get list of currently enabled backend indices from existing backends.toml.

    Args:
        backends_toml_path: Path to existing backends.toml file.
        backend_options: List of backend options to match against.

    Returns:
        List of 0-based indices of currently enabled backends.
    """
    currently_enabled: list[int] = []

    if not path_exists(backends_toml_path):
        return currently_enabled

    try:
        toml_doc = load_toml_from_path(backends_toml_path)

        # Create a mapping of backend_key to index
        backend_key_to_index = {backend_key: idx for idx, (backend_key, _) in enumerate(backend_options)}

        # Find which backends are currently enabled
        for backend_key in toml_doc:
            if backend_key != "internal" and backend_key in backend_key_to_index:
                backend_section = toml_doc[backend_key]
                if isinstance(backend_section, dict):
                    if backend_section.get("enabled", False) is True:  # type: ignore[union-attr]
                        currently_enabled.append(backend_key_to_index[backend_key])

    except Exception:
        # If we can't read the file, just return empty list (silent failure is acceptable here)
        return []

    return sorted(currently_enabled)


class InitFocus(StrEnum):
    """Focus options for initialization."""

    ALL = "all"
    CONFIG = "config"
    INFERENCE = "inference"
    ROUTING = "routing"
    TELEMETRY = "telemetry"


def build_backend_selection_panel(backend_options: list[tuple[str, str]], currently_enabled: list[int] | None = None) -> Panel:
    """Create a Rich Panel for backend selection with options table.

    Args:
        backend_options: List of tuples (backend_key, display_name).
        currently_enabled: Optional list of currently enabled backend indices (0-based).

    Returns:
        A Panel containing the backend selection interface.
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", width=4)
    table.add_column(style="bold", width=30)
    table.add_column(style="dim", width=15)

    for idx, (_, backend_name) in enumerate(backend_options, start=1):
        # Mark currently enabled backends
        status = "[green]✓ enabled[/green]" if currently_enabled and (idx - 1) in currently_enabled else ""
        table.add_row(f"[{idx}]", backend_name, status)

    # Add special options at the end
    table.add_row("[A]", "[dim]all - Select all backends[/dim]", "")
    table.add_row("[Q]", "[dim]quit - Exit without configuring[/dim]", "")

    # Update description based on whether we're showing current selection
    if currently_enabled:
        # Build current selection display with numbers and names
        current_items: list[str] = []
        for idx in sorted(currently_enabled):
            backend_name = backend_options[idx][1]
            current_items.append(f"{idx + 1} ({backend_name})")
        current_selection = ", ".join(current_items)
        description = Text(
            f"Current selection: {current_selection}\n"
            "Select which inference backends you have access to.\n"
            "Enter numbers separated by commas or spaces (e.g., '1,5,6' or '1 5 6'), 'a' for all.\n"
            "Press Enter to keep current selection.",
            style="dim",
        )
    else:
        description = Text(
            "Select which inference backends you have access to.\n"
            "Enter numbers separated by commas or spaces (e.g., '1,5,6' or '1 5 6'), 'a' for all.\n"
            "Press Enter for the recommended default (1).",
            style="dim",
        )

    return Panel(
        Group(description, Text(""), table),
        title="[bold yellow]Inference Backend Selection[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_backend_indices(console: Console, backend_options: list[tuple[str, str]], currently_enabled: list[int] | None = None) -> list[int]:
    """Prompt user to select backend indices with validation.

    Args:
        console: Rich Console instance for user interaction.
        backend_options: List of available backend options.
        currently_enabled: Optional list of currently enabled backend indices (0-based).

    Returns:
        List of validated backend indices (0-based) selected by the user.

    Raises:
        typer.Exit: If user chooses to quit.
    """
    # Determine default based on current selection or fallback to first option
    if currently_enabled:
        default_indices = sorted(currently_enabled)
        default_str = ",".join(str(i + 1) for i in default_indices)
    else:
        default_indices = [0]
        default_str = "1"

    selected_indices: list[int] = []
    while True:
        choice_str = Prompt.ask("[bold]Enter your choices[/bold]", default=default_str, console=console)
        choice_input = choice_str.strip().lower()

        # Handle quit option
        if choice_input in ("q", "quit"):
            console.print("\n[yellow]Exiting without configuring backends.[/yellow]")
            raise typer.Exit(code=0)

        # Handle all option
        if choice_input in ("a", "all"):
            selected_indices = list(range(len(backend_options)))
            break

        # Parse input - handle empty (use default)
        if not choice_input:
            selected_indices = default_indices
            break

        # Split by comma or space
        parts = choice_input.replace(",", " ").split()

        try:
            # Parse as 1-based indices from user input
            user_indices = [int(part.strip()) for part in parts if part.strip()]

            # Validate all indices are in range (1-based)
            invalid_indices = [i for i in user_indices if i < 1 or i > len(backend_options)]
            if invalid_indices:
                max_idx = len(backend_options)
                console.print(
                    f"[red]Invalid choice(s): {invalid_indices}.[/red] "
                    f"Please enter numbers between 1 and {max_idx}, [cyan]a[/cyan] for all, or [cyan]q[/cyan] to quit.\n"
                )
                continue

            # Convert to 0-based indices for internal use
            selected_indices = [i - 1 for i in user_indices]
            break

        except ValueError:
            console.print(
                f"[red]Invalid input: '{choice_str}'.[/red] "
                f"Please enter numbers separated by commas or spaces, [cyan]a[/cyan] for all, or [cyan]q[/cyan] to quit.\n"
            )

    return selected_indices


def display_selected_backends(console: Console, selected_indices: list[int], backend_options: list[tuple[str, str]]) -> None:
    """Display confirmation of selected backends.

    Args:
        console: Rich Console instance for output.
        selected_indices: List of selected backend indices.
        backend_options: List of available backend options.
    """
    selected_names = [backend_options[idx][1] for idx in sorted(selected_indices)]
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
        InitFocus.ROUTING: ("Routing profile", "routing profile"),
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
        if focus == InitFocus.ROUTING:
            console.print(f"[green]✓[/green] {subject} is already configured!")
        else:
            console.print(f"[green]✓[/green] {subject} are already configured!")
        console.print()
        console.print(f"[dim]Configuration file:[/dim] [cyan]{config_path}[/cyan]")
        console.print()

        return Confirm.ask(f"[bold]Would you like to reconfigure {action_verb}?[/bold]", default=False)

    return False


def build_initialization_panel(needs_config: bool, needs_inference: bool, needs_routing: bool, needs_telemetry: bool, reset: bool) -> Panel:
    """Build the initialization confirmation panel.

    Args:
        needs_config: Whether config initialization is needed.
        needs_inference: Whether inference setup is needed.
        needs_routing: Whether routing setup is needed.
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
        if needs_routing:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] routing profile")
        if needs_telemetry:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] telemetry preferences")
    else:
        if needs_config:
            message_parts.append("• Create required configuration files in [cyan].pipelex/[/cyan]")
        if needs_inference:
            message_parts.append("• Ask you to choose your inference backends")
        if needs_routing:
            message_parts.append("• Ask you to configure your routing profile")
        if needs_telemetry:
            message_parts.append("• Ask you to choose your telemetry preferences")

    # Determine title based on what's being initialized
    num_items = sum([needs_config, needs_inference, needs_routing, needs_telemetry])
    if reset:
        if num_items > 1:
            title_text = "[bold yellow]Resetting Configuration[/bold yellow]"
        elif needs_config:
            title_text = "[bold yellow]Resetting Configuration Files[/bold yellow]"
        elif needs_inference:
            title_text = "[bold yellow]Resetting Inference Backends[/bold yellow]"
        elif needs_routing:
            title_text = "[bold yellow]Resetting Routing Profile[/bold yellow]"
        else:
            title_text = "[bold yellow]Resetting Telemetry[/bold yellow]"
    elif num_items > 1:
        title_text = "[bold cyan]Pipelex Initialization[/bold cyan]"
    elif needs_config:
        title_text = "[bold cyan]Configuration Setup[/bold cyan]"
    elif needs_inference:
        title_text = "[bold cyan]Inference Backend Setup[/bold cyan]"
    elif needs_routing:
        title_text = "[bold cyan]Routing Profile Setup[/bold cyan]"
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


def build_primary_backend_panel(backend_keys: list[str], backend_options: list[tuple[str, str]]) -> Panel:
    """Build a panel for selecting a primary backend from enabled backends.

    Args:
        backend_keys: List of enabled backend keys.
        backend_options: List of all backend options to get display names.

    Returns:
        A Panel containing the primary backend selection interface.
    """
    # Create a mapping of backend_key to display_name
    backend_key_to_name = dict(backend_options)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", width=4)
    table.add_column(style="bold", width=30)

    for idx, backend_key in enumerate(backend_keys, start=1):
        display_name = backend_key_to_name.get(backend_key, snake_to_capitalize_first_letter(backend_key))
        table.add_row(f"[{idx}]", display_name)

    description = Text(
        "Multiple backends are enabled. Select which backend should be your primary/default.\n"
        "The primary backend will be used for models that don't have an exact match or pattern match in your routes.",
        style="dim",
    )

    return Panel(
        Group(description, Text(""), table),
        title="[bold yellow]Primary Backend Selection[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_primary_backend(console: Console, backend_keys: list[str]) -> str:
    """Prompt user to select a primary backend from enabled backends.

    Args:
        console: Rich Console instance for user interaction.
        backend_keys: List of enabled backend keys.

    Returns:
        The selected backend key.
    """
    # Default to first backend
    default_str = "1"

    selected_backend: str | None = None
    while selected_backend is None:
        choice_str = Prompt.ask("[bold]Enter your choice[/bold]", default=default_str, console=console)
        choice_input = choice_str.strip()

        # Parse input - handle empty (use default)
        if not choice_input:
            selected_backend = backend_keys[0]
            break

        try:
            # Parse as 1-based index from user input
            user_index = int(choice_input)

            # Validate index is in range (1-based)
            if user_index < 1 or user_index > len(backend_keys):
                max_idx = len(backend_keys)
                console.print(f"[red]Invalid choice: {user_index}.[/red] Please enter a number between 1 and {max_idx}.\n")
                continue

            # Convert to 0-based index and get backend key
            selected_backend = backend_keys[user_index - 1]
            break

        except ValueError:
            console.print(f"[red]Invalid input: '{choice_str}'.[/red] Please enter a number.\n")

    return selected_backend


def build_fallback_order_panel(remaining_backends: list[str], backend_options: list[tuple[str, str]]) -> Panel:
    """Build a panel explaining fallback order configuration.

    Args:
        remaining_backends: List of backend keys (excluding primary).
        backend_options: List of all backend options to get display names.

    Returns:
        A Panel containing the fallback order explanation and current order.
    """
    # Create a mapping of backend_key to display_name
    backend_key_to_name = dict(backend_options)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", width=4)
    table.add_column(style="bold", width=30)

    for idx, backend_key in enumerate(remaining_backends, start=1):
        display_name = backend_key_to_name.get(backend_key, snake_to_capitalize_first_letter(backend_key))
        table.add_row(f"[{idx}]", display_name)

    description = Text(
        "Fallback order determines which backends to try when a model has no exact match or pattern match\n"
        "and is not available in your default backend.\nCurrent order:",
        style="dim",
    )

    return Panel(
        Group(description, Text(""), table),
        title="[bold yellow]Fallback Backend Order[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def prompt_fallback_order(console: Console, remaining_backends: list[str], backend_options: list[tuple[str, str]]) -> list[str]:
    """Prompt user to order the remaining backends for fallback.

    Args:
        console: Rich Console instance for user interaction.
        remaining_backends: List of backend keys (excluding primary).
        backend_options: List of all backend options to get display names.

    Returns:
        Ordered list of backend keys for fallback.
    """
    backend_key_to_name = dict(backend_options)

    console.print()
    console.print("[dim]Enter the order of backends (space or comma separated indices).[/dim]")
    console.print("[dim]For example: '2 1 3' or '2,1,3' to reorder them.[/dim]")
    console.print()

    fallback_order: list[str] | None = None
    while fallback_order is None:
        # Show current order as default
        default_order = " ".join(str(i + 1) for i in range(len(remaining_backends)))
        choice_str = Prompt.ask("[bold]Enter order[/bold]", default=default_order, console=console)
        choice_input = choice_str.strip()

        # Handle empty input (use default order)
        if not choice_input:
            fallback_order = remaining_backends.copy()
            break

        # Split by comma or space
        parts = choice_input.replace(",", " ").split()

        try:
            # Parse as 1-based indices from user input
            user_indices = [int(part.strip()) for part in parts if part.strip()]

            # Validate: must have exactly the same number of indices
            if len(user_indices) != len(remaining_backends):
                console.print(f"[red]Error: You must specify all {len(remaining_backends)} backends.[/red] You provided {len(user_indices)}.\n")
                continue

            # Validate: all indices are in range (1-based)
            invalid_indices = [i for i in user_indices if i < 1 or i > len(remaining_backends)]
            if invalid_indices:
                max_idx = len(remaining_backends)
                console.print(f"[red]Invalid choice(s): {invalid_indices}.[/red] Please enter numbers between 1 and {max_idx}.\n")
                continue

            # Validate: no duplicates
            if len(user_indices) != len(set(user_indices)):
                console.print("[red]Error: Duplicate indices not allowed.[/red] Each backend must appear exactly once.\n")
                continue

            # Convert to 0-based indices and reorder backends
            zero_based_indices = [i - 1 for i in user_indices]
            fallback_order = [remaining_backends[i] for i in zero_based_indices]
            break

        except ValueError:
            console.print(f"[red]Invalid input: '{choice_str}'.[/red] Please enter numbers separated by commas or spaces.\n")

    # Display the final order
    console.print("\n[green]✓[/green] Fallback order set to:")
    for idx, backend_key in enumerate(fallback_order, start=1):
        display_name = backend_key_to_name.get(backend_key, snake_to_capitalize_first_letter(backend_key))
        console.print(f"   {idx}. {display_name}")

    return fallback_order


def display_routing_profile_result(console: Console, profile_name: str, created: bool = False) -> None:
    """Display confirmation of routing profile configuration.

    Args:
        console: Rich Console instance for output.
        profile_name: Name of the routing profile that was set.
        created: Whether the profile was newly created.
    """
    if created:
        console.print(f"\n[green]✓[/green] Created and set routing profile to: [bold cyan]{profile_name}[/bold cyan]")
    else:
        console.print(f"\n[green]✓[/green] Routing profile set to: [bold cyan]{profile_name}[/bold cyan]")
