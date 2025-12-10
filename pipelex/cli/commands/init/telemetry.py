"""Telemetry configuration logic for the init command."""

import os
import shutil

from rich.console import Console

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME


def setup_telemetry(console: Console, telemetry_config_path: str) -> None:
    """Set up telemetry configuration by copying the template.

    Args:
        console: Rich Console instance for user interaction.
        telemetry_config_path: Path to save the telemetry configuration.
    """
    # Ensure parent directory exists (needed when running `pipelex init telemetry` on fresh project)
    os.makedirs(os.path.dirname(telemetry_config_path), exist_ok=True)

    # Copy template to destination
    template_path = os.path.join(str(get_kit_configs_dir()), TELEMETRY_CONFIG_FILE_NAME)
    shutil.copy(template_path, telemetry_config_path)

    console.print()
    console.print("[green]✓[/green] Telemetry configuration created")
    console.print(f"  [dim]File:[/dim] [cyan]{telemetry_config_path}[/cyan]")
    console.print()
    console.print("[dim]Edit this file to configure AI trace destinations:[/dim]")
    console.print("[dim]  • \\[posthog] - Send traces to your own PostHog project[/dim]")
    console.print("[dim]  • \\[langfuse] - Enable Langfuse LLM observability[/dim]")
    console.print("[dim]  • \\[\\[otlp]] - Add custom OpenTelemetry exporters[/dim]")
    console.print()
    console.print("[dim]💡 Note: If you use Pipelex Gateway, separate telemetry is sent to Pipelex[/dim]")
    console.print("[dim]servers regardless of these settings.[/dim]")
