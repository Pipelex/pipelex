"""UI components for backend configuration in the init command."""

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter
from pipelex.tools.misc.toml_utils import load_toml_from_path


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
