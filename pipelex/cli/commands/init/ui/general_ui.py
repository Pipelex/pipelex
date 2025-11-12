"""General UI components for the init command."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from pipelex.cli.commands.init.ui.types import InitFocus


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
