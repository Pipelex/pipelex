"""Telemetry configuration logic for the init command."""

import shutil
from pathlib import Path

from rich.console import Console

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TELEMETRY_PROJECT_TEMPLATE_FILE_NAME


def setup_telemetry(console: Console, telemetry_config_path: Path, for_project: bool) -> None:
    """Set up telemetry configuration by copying the appropriate kit template.

    The global template (`telemetry.toml`) carries active defaults and seeds
    `~/.pipelex/telemetry.toml`. The project template (`telemetry.project.toml`)
    is fully commented out so a project's `.pipelex/telemetry.toml` does not
    override the user's global telemetry settings during layered loading.

    Args:
        console: Rich Console instance for user interaction.
        telemetry_config_path: Path to save the telemetry configuration.
        for_project: True when targeting a project's `.pipelex/`; False when
            targeting the global `~/.pipelex/`.
    """
    telemetry_config_path.parent.mkdir(parents=True, exist_ok=True)

    template_name = TELEMETRY_PROJECT_TEMPLATE_FILE_NAME if for_project else TELEMETRY_CONFIG_FILE_NAME
    template_path = Path(str(get_kit_configs_dir())) / template_name
    shutil.copy(template_path, telemetry_config_path)

    console.print()
    console.print("[green]✓[/green] Telemetry configuration created")
    console.print(f"  [dim]File:[/dim] [cyan]{telemetry_config_path}[/cyan]")
    console.print()
    if for_project:
        console.print("[dim]Project telemetry inherits your global settings. Uncomment any key[/dim]")
        console.print("[dim]in this file to override it for this project only.[/dim]")
    else:
        console.print("[dim]Edit this file to configure AI trace destinations:[/dim]")
        console.print("[dim]  • \\[posthog] - Send traces to your own PostHog project[/dim]")
        console.print("[dim]  • \\[langfuse] - Enable Langfuse LLM observability[/dim]")
        console.print("[dim]  • \\[\\[otlp]] - Add custom OpenTelemetry exporters[/dim]")
    console.print()
    console.print("[dim]💡 Note: If you use Pipelex Gateway, separate telemetry is sent to Pipelex[/dim]")
    console.print("[dim]servers regardless of these settings.[/dim]")
