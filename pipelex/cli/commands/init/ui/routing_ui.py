"""UI components for routing profile configuration in the init command."""

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter


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
