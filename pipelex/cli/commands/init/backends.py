"""Backend configuration logic for the init command."""

import os
from typing import Any

from pipelex.cli.commands.init.ui.backends_ui import (
    build_backend_selection_panel,
    display_selected_backends,
    get_backend_options_from_toml,
    get_currently_enabled_backends,
    prompt_backend_select,
)
from pipelex.cli.commands.init.ui.gateway_ui import (
    display_gateway_accepted_message,
    display_gateway_declined_message,
    prompt_gateway_acceptance,
)
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.hub import get_console
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.pipelex_service_agreement import update_service_terms_acceptance
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
                # Only include backends that are explicitly enabled
                if backend_section.get("enabled", False) is True:  # type: ignore[union-attr]
                    selected_backends.append(backend_key)

    return selected_backends


def disable_gateway_backend(backends_toml_path: str) -> None:
    """Disable the pipelex_gateway backend in backends.toml.

    Args:
        backends_toml_path: Path to the backends.toml file.
    """
    if not path_exists(backends_toml_path):
        return

    toml_doc = load_toml_with_tomlkit(backends_toml_path)

    if PipelexBackend.GATEWAY in toml_doc:
        toml_doc[PipelexBackend.GATEWAY]["enabled"] = False  # type: ignore[index]
        save_toml_to_path(toml_doc, backends_toml_path)


def customize_backends_config(is_first_time_setup: bool = False) -> None:
    """Interactively customize which inference backends are enabled in backends.toml.

    Args:
        is_first_time_setup: Whether this is the first time backends.toml is being set up.
    """
    console = get_console()
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

        # If this is first-time setup, ignore what's in the template (all enabled)
        # and use only pipelex_gateway as the default
        if is_first_time_setup or (currently_enabled and len(currently_enabled) == len(backend_options)):
            currently_enabled = []

        # Load the backends.toml file
        toml_doc = load_toml_with_tomlkit(backends_toml_path)
        console.print()

        # UI: Display panel and get user selection
        console.print(build_backend_selection_panel(backend_options, currently_enabled, is_first_time_setup))
        selected_indices, selected_backends = prompt_backend_select(
            console=console,
            backend_options=backend_options,
            currently_enabled=currently_enabled,
            is_first_time_setup=is_first_time_setup,
        )

        # Check if pipelex_gateway is selected and handle terms acceptance
        if PipelexBackend.GATEWAY in selected_backends:
            gateway_accepted = prompt_gateway_acceptance(console)

            if gateway_accepted:
                display_gateway_accepted_message(console)
                update_service_terms_acceptance(accepted=True)
            else:
                display_gateway_declined_message(console)
                update_service_terms_acceptance(accepted=False)

                # Remove pipelex_gateway from selected indices
                selected_indices = [idx for idx in selected_indices if backend_options[idx][0] != PipelexBackend.GATEWAY]

        # Business logic: Update TOML
        update_backends_in_toml(toml_doc, selected_indices, backend_options)
        save_toml_to_path(toml_doc, backends_toml_path)

        # UI: Display confirmation
        display_selected_backends(console, selected_indices, backend_options)

    except Exception as exc:
        console.print(f"[yellow]⚠ Warning: Failed to customize backends: {exc}[/yellow]")
        console.print("[dim]You can manually edit .pipelex/inference/backends.toml later[/dim]")
