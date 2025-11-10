"""Routing profile configuration logic for the init command."""

import os
from typing import Any

from rich.console import Console
from rich.prompt import Confirm
from tomlkit import table

from pipelex.cli.commands.init.ui.backends_ui import get_backend_options_from_toml
from pipelex.cli.commands.init.ui.routing_ui import (
    build_fallback_order_panel,
    build_primary_backend_panel,
    display_routing_profile_result,
    prompt_fallback_order,
    prompt_primary_backend,
)
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path


def customize_routing_profile(selected_backend_keys: list[str]) -> None:
    """Interactively customize routing profile based on selected backends.

    Args:
        selected_backend_keys: List of backend keys that are enabled.
    """
    console = Console()
    routing_profiles_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "routing_profiles.toml")
    template_routing_path = os.path.join(str(get_kit_configs_dir()), "inference", "routing_profiles.toml")
    backends_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "backends.toml")

    if not path_exists(routing_profiles_toml_path):
        console.print("[yellow]⚠ Warning: routing_profiles.toml not found, skipping routing customization[/yellow]")
        return

    try:
        # Load template for reference (to check if profiles exist)
        template_toml = load_toml_with_tomlkit(template_routing_path)

        # Load the user's routing_profiles.toml file
        toml_doc = load_toml_with_tomlkit(routing_profiles_toml_path)

        # Get backend options for display names
        template_backends_path = os.path.join(str(get_kit_configs_dir()), "inference", "backends.toml")
        backend_options = get_backend_options_from_toml(template_backends_path, backends_toml_path)

        # Case 1: pipelex_inference is enabled - keep pipelex_first
        if "pipelex_inference" in selected_backend_keys:
            toml_doc["active"] = "pipelex_first"
            save_toml_to_path(toml_doc, routing_profiles_toml_path)
            display_routing_profile_result(console, "pipelex_first", created=False)
            return

        # Case 2: Only one backend selected - use all_{backend_key} profile
        if len(selected_backend_keys) == 1:
            backend_key = selected_backend_keys[0]
            profile_name = f"all_{backend_key}"

            # Check if profile exists in template
            template_profiles: dict[str, Any] = template_toml.get("profiles") or {}  # type: ignore[assignment]
            profile_exists = profile_name in template_profiles

            if not profile_exists:
                # Ask for confirmation to create the profile
                console.print()
                console.print(f"[yellow]Profile {profile_name!r} does not exist in the template.[/yellow]")
                if not Confirm.ask("[bold]Would you like to create it?[/bold]", default=True):
                    console.print("[dim]Keeping current routing profile configuration.[/dim]")
                    return

                # Create the profile
                if "profiles" not in toml_doc:
                    toml_doc["profiles"] = {}

                # Use a dict for the profile data
                profile_data = {
                    "description": f"Use {backend_key} backend for all its supported models",
                    "default": backend_key,
                }
                toml_doc["profiles"][profile_name] = profile_data  # type: ignore[index]

            # Set as active profile
            toml_doc["active"] = profile_name
            save_toml_to_path(toml_doc, routing_profiles_toml_path)
            display_routing_profile_result(console, profile_name, created=not profile_exists)
            return

        # Case 3: Multiple backends (no pipelex_inference) - create/update custom_routing profile
        console.print()
        console.print("[cyan]Setting up routing for multiple backends...[/cyan]")
        console.print()

        # Show panel and prompt for primary backend
        console.print(build_primary_backend_panel(selected_backend_keys, backend_options))
        primary_backend = prompt_primary_backend(console, selected_backend_keys)

        # Prompt for fallback order if there are 2+ remaining backends
        remaining_backends = [b for b in selected_backend_keys if b != primary_backend]
        fallback_order: list[str] | None = None

        if len(remaining_backends) >= 2:
            console.print()
            console.print(build_fallback_order_panel(remaining_backends, backend_options))
            # Get the ordered remaining backends from user (default keeps current order)
            ordered_remaining = prompt_fallback_order(console, remaining_backends, backend_options)
            fallback_order = [primary_backend, *ordered_remaining]
        elif len(remaining_backends) == 1:
            # Only one remaining backend - set fallback_order with primary first
            fallback_order = [primary_backend, *remaining_backends]
        else:
            # Only primary backend selected - no fallback needed
            fallback_order = None

        # Create or update custom_routing profile
        if "profiles" not in toml_doc:
            toml_doc["profiles"] = {}

        # Insert custom_routing at the beginning of profiles (after standard profiles if they exist)
        # We'll create a new profiles dict with custom_routing first
        new_profiles = table()

        # Create custom_routing profile with nested routes table
        custom_routing_profile = table()
        custom_routing_profile["description"] = "Custom routing"
        custom_routing_profile["default"] = primary_backend
        if fallback_order:
            custom_routing_profile["fallback_order"] = fallback_order
        custom_routing_profile["routes"] = table()
        new_profiles["custom_routing"] = custom_routing_profile

        # Copy existing profiles after custom_routing
        existing_profiles: dict[str, Any] = toml_doc.get("profiles") or {}  # type: ignore[assignment]
        for profile_key, profile_value in existing_profiles.items():  # type: ignore[union-attr]
            if profile_key != "custom_routing":
                new_profiles[profile_key] = profile_value

        toml_doc["profiles"] = new_profiles  # type: ignore[assignment]
        toml_doc["active"] = "custom_routing"

        save_toml_to_path(toml_doc, routing_profiles_toml_path)
        display_routing_profile_result(console, "custom_routing", created=True)

        # Inform user about customization options
        console.print("[dim]You can find your custom routing profile in:[/dim]")
        console.print(f"[dim]  {routing_profiles_toml_path}[/dim]")
        console.print("[dim]You can further customize which models get used on which backend by editing the routes section.[/dim]")

    except Exception as exc:
        console.print(f"[yellow]⚠ Warning: Failed to customize routing profile: {exc}[/yellow]")
        console.print("[dim]You can manually edit .pipelex/inference/routing_profiles.toml later[/dim]")
