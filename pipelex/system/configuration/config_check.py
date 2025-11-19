from rich.panel import Panel

from pipelex.cli.commands.init.config_files import init_config
from pipelex.hub import get_console
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.tools.misc.file_utils import path_exists
from pipelex.urls import URLs


def check_is_initialized(print_warning_if_not: bool = True) -> bool:
    backends_toml_path = ConfigPaths.BACKENDS_FILE_PATH
    routing_profiles_toml_path = ConfigPaths.ROUTING_PROFILES_FILE_PATH

    # Check critical files
    config_exists = init_config(reset=False, dry_run=True) == 0
    backends_exists = path_exists(backends_toml_path)
    routing_exists = path_exists(routing_profiles_toml_path)

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
