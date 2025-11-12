"""Telemetry configuration logic for the init command."""

import os

from rich.console import Console

from pipelex.cli.commands.init.ui.telemetry_ui import build_telemetry_selection_panel, prompt_telemetry_mode
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryMode
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


def setup_telemetry(console: Console, telemetry_config_path: str) -> TelemetryMode:
    """Set up telemetry configuration interactively.

    Args:
        console: Rich Console instance for user interaction.
        telemetry_config_path: Path to save the telemetry configuration.

    Returns:
        The selected TelemetryMode.

    Raises:
        typer.Exit: If user chooses to quit.
    """
    console.print()
    console.print(build_telemetry_selection_panel())

    telemetry_mode = prompt_telemetry_mode(console)

    # Save telemetry config
    template_path = os.path.join(str(get_kit_configs_dir()), TELEMETRY_CONFIG_FILE_NAME)
    toml_doc = load_toml_with_tomlkit(template_path)
    toml_doc["telemetry_mode"] = telemetry_mode
    save_toml_to_path(toml_doc, telemetry_config_path)

    console.print(f"\n[green]✓[/green] Telemetry mode set to: [bold cyan]{telemetry_mode}[/bold cyan]")

    return telemetry_mode
