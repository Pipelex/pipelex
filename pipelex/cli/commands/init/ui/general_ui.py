"""General UI components for the init command."""

from rich.panel import Panel


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
