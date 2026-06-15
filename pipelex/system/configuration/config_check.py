from rich.panel import Panel

from pipelex.hub import get_console
from pipelex.system.configuration.config_loader import CONFIG_NAME, config_manager
from pipelex.tools.misc.file_utils import path_exists
from pipelex.urls import URLs

# Config files that must be resolvable (in project or global dir) for pipelex to be initialized.
PLXT_CONFIG_NAME = "plxt.toml"


def check_is_initialized(*, print_warning_if_not: bool = True) -> bool:
    # Use resolve_config_file for all checks — consistent with how backends and routing are resolved
    config_exists = path_exists(config_manager.resolve_config_file(CONFIG_NAME)) and path_exists(config_manager.resolve_config_file(PLXT_CONFIG_NAME))
    backends_exists = path_exists(config_manager.backends_file_path)
    routing_exists = path_exists(config_manager.routing_profiles_file_path)

    is_initialized = config_exists and backends_exists and routing_exists

    if not is_initialized and print_warning_if_not:
        console = get_console()

        # Build a descriptive message about what's missing
        issues: list[str] = []
        if not config_exists:
            issues.append("[yellow]•[/yellow] Configuration files not configured")
        if not backends_exists:
            issues.append("[yellow]•[/yellow] Inference backends not configured")
        if not routing_exists:
            issues.append("[yellow]•[/yellow] Routing profiles not configured")

        issues_text = "\n".join(issues) if issues else "[yellow]•[/yellow] Configuration incomplete"

        message = f"""[bold red]⚠️  Pipelex is not initialized[/bold red]

{issues_text}

[bold cyan]To initialize Pipelex, run:[/bold cyan]

[bold green]pipelex init[/bold green]

This will set up all required configuration files and guide you through
selecting inference backends and routing profiles.

[dim]Need help? Visit our Discord: {URLs.discord}[/dim]"""

        panel = Panel(
            message,
            border_style="red",
            padding=(1, 2),
        )

        console.print()
        console.print(panel)
        console.print()
    return is_initialized
