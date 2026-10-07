"""General UI components for the init command."""

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.commands.init.credentials import get_global_env_path


def build_initialization_panel(
    *,
    needs_config: bool,
    needs_inference: bool,
    needs_routing: bool,
    needs_telemetry: bool,
    reset: bool,
    check_credentials: bool = False,
    asks_setup_path: bool = False,
) -> Panel:
    """Build the initialization confirmation panel.

    Args:
        needs_config: Whether config initialization is needed.
        needs_inference: Whether inference setup is needed.
        needs_routing: Whether routing setup is needed.
        needs_telemetry: Whether telemetry setup is needed.
        reset: Whether this is a reset operation.
        check_credentials: Whether credential prompting will happen.
        asks_setup_path: Whether the run asks where runs execute, the hosted Pipelex API or this machine, whose
            answer decides the inference and credential steps.

    Returns:
        A Panel containing the initialization confirmation message.
    """
    # Build message based on what's being initialized
    message_parts: list[str] = []
    credentials_file = escape(str(get_global_env_path()))
    if asks_setup_path:
        if needs_config:
            verb = "[yellow]Reset and reconfigure[/yellow]" if reset else "Create"
            message_parts.append(f"• {verb} configuration files in [cyan].pipelex/[/cyan]")
        message_parts.append("• Ask where your runs execute:")
        message_parts.append("    on the hosted Pipelex API: sign in to get a Pipelex API key (default)")
        message_parts.append(
            f"    on this machine: choose your inference backends and enter their API keys (saved to [cyan]{credentials_file}[/cyan])"
        )
        message_parts.append("• Suggest IDE extension for [cyan].mthds[/cyan] syntax highlighting")
        if needs_telemetry:
            verb = "[yellow]Reset and reconfigure[/yellow]" if reset else "Choose"
            message_parts.append(f"• {verb} telemetry preferences")
    elif reset:
        if needs_config:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] configuration files in [cyan].pipelex/[/cyan]")
        if needs_inference:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] inference backends")
            message_parts.append("• Suggest IDE extension for [cyan].mthds[/cyan] syntax highlighting")
        if check_credentials:
            message_parts.append(f"• Prompt for missing API keys (saved to [cyan]{credentials_file}[/cyan])")
        if needs_routing:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] routing profile")
        if needs_telemetry:
            message_parts.append("• [yellow]Reset and reconfigure[/yellow] telemetry preferences")
    else:
        if needs_config:
            message_parts.append("• Create required configuration files in [cyan].pipelex/[/cyan]")
        if needs_inference:
            message_parts.append("• Ask you to choose your inference backends")
            message_parts.append("• Suggest IDE extension for [cyan].mthds[/cyan] syntax highlighting")
        if check_credentials:
            message_parts.append(f"• Prompt for missing API keys (saved to [cyan]{credentials_file}[/cyan])")
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
