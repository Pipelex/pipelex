"""UI components for telemetry configuration in the init command."""

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from pipelex.system.telemetry.telemetry_config import TelemetryMode


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
