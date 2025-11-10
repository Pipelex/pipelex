"""Backend configuration logic for the init command."""

import os
from typing import Any

from rich.console import Console

from pipelex.cli.commands.init.ui.backends_ui import (
    build_backend_selection_panel,
    display_selected_backends,
    get_backend_options_from_toml,
    get_currently_enabled_backends,
    prompt_backend_indices,
)
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path


def update_backends_in_toml(toml_doc: Any, selected_indices: list[int], backend_options: list[tuple[str, str]]) -> None:
    """Update the backends.toml document with selected backends.

    Args:
        toml_doc: The TOML document to update.
        selected_indices: List of backend indices to enable.
        backend_options: List of available backend options.
    """
    selected_backend_keys = {backend_options[idx][0] for idx in selected_indices}

    # Disable all backends first (except internal)
    for backend_key in toml_doc:
        if backend_key != "internal" and backend_key in toml_doc:
            backend_section = toml_doc[backend_key]
            # Set enabled field based on selection (works with tomlkit's special types)
            backend_section["enabled"] = backend_key in selected_backend_keys  # type: ignore[index]


def get_selected_backend_keys(backends_toml_path: str) -> list[str]:
    """Extract the list of enabled backend keys from backends.toml.

    Args:
        backends_toml_path: Path to the backends.toml file.

    Returns:
        List of backend keys that are enabled (excluding 'internal').
    """
    selected_backends: list[str] = []

    if not path_exists(backends_toml_path):
        return selected_backends

    toml_doc = load_toml_from_path(backends_toml_path)

    for backend_key in toml_doc:
        if backend_key != "internal":
            backend_section = toml_doc[backend_key]
            if isinstance(backend_section, dict):
                if (setting := backend_section.get("enabled")) is not None and not setting:  # type: ignore[reportUnknownMemberType]
                    continue
                selected_backends.append(backend_key)

    return selected_backends


def customize_backends_config() -> None:
    """Interactively customize which inference backends are enabled in backends.toml."""
    console = Console()
    backends_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "backends.toml")
    template_backends_path = os.path.join(str(get_kit_configs_dir()), "inference", "backends.toml")

    if not path_exists(backends_toml_path):
        console.print("[yellow]⚠ Warning: backends.toml not found, skipping backend customization[/yellow]")
        return

    try:
        # Get backend options from template and existing config
        existing_path = backends_toml_path if path_exists(backends_toml_path) else None
        backend_options = get_backend_options_from_toml(template_backends_path, existing_path)

        # Get currently enabled backends to show user their current selection
        currently_enabled = get_currently_enabled_backends(backends_toml_path, backend_options)

        # Load the backends.toml file
        toml_doc = load_toml_with_tomlkit(backends_toml_path)
        console.print()

        # UI: Display panel and get user selection
        console.print(build_backend_selection_panel(backend_options, currently_enabled))
        selected_indices = prompt_backend_indices(console, backend_options, currently_enabled)

        # Business logic: Update TOML
        update_backends_in_toml(toml_doc, selected_indices, backend_options)
        save_toml_to_path(toml_doc, backends_toml_path)

        # UI: Display confirmation
        display_selected_backends(console, selected_indices, backend_options)

    except Exception as exc:
        console.print(f"[yellow]⚠ Warning: Failed to customize backends: {exc}[/yellow]")
        console.print("[dim]You can manually edit .pipelex/inference/backends.toml later[/dim]")
