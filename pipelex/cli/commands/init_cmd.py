import os
import shutil
from typing import Any

import typer
from rich.console import Console
from rich.prompt import Confirm
from tomlkit import table

from pipelex.cli.commands.init_ui import (
    InitFocus,
    build_backend_selection_panel,
    build_fallback_order_panel,
    build_initialization_panel,
    build_primary_backend_panel,
    build_telemetry_selection_panel,
    display_already_configured_message,
    display_routing_profile_result,
    display_selected_backends,
    get_backend_options_from_toml,
    get_currently_enabled_backends,
    prompt_backend_indices,
    prompt_fallback_order,
    prompt_primary_backend,
    prompt_telemetry_mode,
)
from pipelex.exceptions import PipelexCLIError
from pipelex.kit.paths import get_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
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
                if backend_section.get("enabled", False) is True:  # pyright: ignore[reportUnknownMemberType]
                    selected_backends.append(backend_key)

    return selected_backends


def customize_backends_config() -> None:
    """Interactively customize which inference backends are enabled in backends.toml."""
    console = Console()
    backends_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "backends.toml")
    template_backends_path = os.path.join(str(get_configs_dir()), "inference", "backends.toml")

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


def customize_routing_profile(selected_backend_keys: list[str]) -> None:
    """Interactively customize routing profile based on selected backends.

    Args:
        selected_backend_keys: List of backend keys that are enabled.
    """
    console = Console()
    routing_profiles_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "routing_profiles.toml")
    template_routing_path = os.path.join(str(get_configs_dir()), "inference", "routing_profiles.toml")
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
        template_backends_path = os.path.join(str(get_configs_dir()), "inference", "backends.toml")
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


def init_config(reset: bool = False, dry_run: bool = False) -> int:
    """Initialize pipelex configuration in the .pipelex directory. Does not install telemetry, just the main config dans inference backends.

    Args:
        reset: Whether to overwrite existing files.
        dry_run: Whether to only print the files that would be copied, without actually copying them.

    Returns:
        The number of files copied.
    """
    config_template_dir = str(get_configs_dir())
    target_config_dir = config_manager.pipelex_config_dir

    os.makedirs(target_config_dir, exist_ok=True)

    try:
        copied_files: list[str] = []
        existing_files: list[str] = []

        def copy_directory_structure(src_dir: str, dst_dir: str, relative_path: str = "", dry_run: bool = False) -> None:
            """Recursively copy directory structure, handling existing files."""
            for item in os.listdir(src_dir):
                src_item = os.path.join(src_dir, item)
                dst_item = os.path.join(dst_dir, item)
                relative_item = os.path.join(relative_path, item) if relative_path else item

                # Skip telemetry.toml - it will be created when user is prompted
                if item == TELEMETRY_CONFIG_FILE_NAME:
                    continue

                if os.path.isdir(src_item):
                    if not dry_run:
                        os.makedirs(dst_item, exist_ok=True)
                    copy_directory_structure(src_item, dst_item, relative_item, dry_run)
                elif os.path.exists(dst_item) and not reset:
                    existing_files.append(relative_item)
                else:
                    if not dry_run:
                        shutil.copy2(src_item, dst_item)
                    copied_files.append(relative_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=target_config_dir, dry_run=dry_run)

        if dry_run:
            return len(copied_files)

        # Report results
        if copied_files:
            typer.echo(f"✅ Copied {len(copied_files)} files to {target_config_dir}:")
            for file in sorted(copied_files):
                typer.echo(f"   • {file}")

        if existing_files:
            typer.echo(f"ℹ️  Skipped {len(existing_files)} existing files (use --reset to overwrite):")
            for file in sorted(existing_files):
                typer.echo(f"   • {file}")

        if not copied_files and not existing_files:
            typer.echo(f"✅ Configuration directory {target_config_dir} is already up to date")

    except Exception as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)


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
    template_path = os.path.join(str(get_configs_dir()), TELEMETRY_CONFIG_FILE_NAME)
    toml_doc = load_toml_with_tomlkit(template_path)
    toml_doc["telemetry_mode"] = telemetry_mode
    save_toml_to_path(toml_doc, telemetry_config_path)

    console.print(f"\n[green]✓[/green] Telemetry mode set to: [bold cyan]{telemetry_mode}[/bold cyan]")

    return telemetry_mode


def determine_needs(
    reset: bool,
    check_config: bool,
    check_inference: bool,
    check_routing: bool,
    check_telemetry: bool,
    backends_toml_path: str,
    routing_profiles_toml_path: str,
    telemetry_config_path: str,
) -> tuple[bool, bool, bool, bool]:
    """Determine what needs to be initialized based on current state.

    Args:
        reset: Whether this is a reset operation.
        check_config: Whether to check config files.
        check_inference: Whether to check inference setup.
        check_routing: Whether to check routing setup.
        check_telemetry: Whether to check telemetry setup.
        backends_toml_path: Path to backends.toml file.
        routing_profiles_toml_path: Path to routing_profiles.toml file.
        telemetry_config_path: Path to telemetry config file.

    Returns:
        Tuple of (needs_config, needs_inference, needs_routing, needs_telemetry) booleans.
    """
    nb_missing_config_files = init_config(reset=False, dry_run=True) if check_config else 0
    needs_config = check_config and (nb_missing_config_files > 0 or reset)
    needs_inference = check_inference and (not path_exists(backends_toml_path) or reset)
    needs_routing = check_routing and (not path_exists(routing_profiles_toml_path) or reset)
    needs_telemetry = check_telemetry and (not path_exists(telemetry_config_path) or reset)

    return needs_config, needs_inference, needs_routing, needs_telemetry


def handle_already_configured(
    focus: InitFocus,
    console: Console,
    backends_toml_path: str,
    routing_profiles_toml_path: str,
    telemetry_config_path: str,
) -> bool:
    """Handle the case when everything is already configured.

    Args:
        focus: The initialization focus area.
        console: Rich Console instance for output.
        backends_toml_path: Path to backends.toml file.
        routing_profiles_toml_path: Path to routing_profiles.toml file.
        telemetry_config_path: Path to telemetry config file.

    Returns:
        True if user wants to reconfigure, False otherwise.
    """
    # Map focus to config path for display
    config_path_map = {
        InitFocus.INFERENCE: backends_toml_path,
        InitFocus.ROUTING: routing_profiles_toml_path,
        InitFocus.TELEMETRY: telemetry_config_path,
        InitFocus.CONFIG: ".pipelex/",
    }

    config_path = config_path_map.get(focus, "")
    return display_already_configured_message(focus, console, config_path)


def update_needs_for_reconfigure(focus: InitFocus) -> tuple[bool, bool, bool, bool]:
    """Update needs flags when user wants to reconfigure.

    Args:
        focus: The initialization focus area.

    Returns:
        Tuple of (needs_config, needs_inference, needs_routing, needs_telemetry) booleans.
    """
    needs_config = focus == InitFocus.CONFIG
    needs_inference = focus == InitFocus.INFERENCE
    needs_routing = focus == InitFocus.ROUTING
    needs_telemetry = focus == InitFocus.TELEMETRY

    return needs_config, needs_inference, needs_routing, needs_telemetry


def confirm_initialization(
    console: Console,
    needs_config: bool,
    needs_inference: bool,
    needs_routing: bool,
    needs_telemetry: bool,
    reset: bool,
    focus: InitFocus,
) -> bool:
    """Ask user to confirm initialization.

    Args:
        console: Rich Console instance for user interaction.
        needs_config: Whether config initialization is needed.
        needs_inference: Whether inference setup is needed.
        needs_routing: Whether routing setup is needed.
        needs_telemetry: Whether telemetry setup is needed.
        reset: Whether this is a reset operation.
        focus: The initialization focus area.

    Returns:
        True if user confirms, False otherwise.

    Raises:
        typer.Exit: If user cancels initialization.
    """
    console.print()
    console.print(build_initialization_panel(needs_config, needs_inference, needs_routing, needs_telemetry, reset))

    if not Confirm.ask("[bold]Continue with initialization?[/bold]", default=True):
        console.print("\n[yellow]Initialization cancelled.[/yellow]")
        if needs_config or needs_inference or needs_routing or needs_telemetry:
            match focus:
                case InitFocus.ALL:
                    init_cmd_str = "pipelex init"
                case InitFocus.CONFIG | InitFocus.INFERENCE | InitFocus.ROUTING | InitFocus.TELEMETRY:
                    init_cmd_str = f"pipelex init {focus}"
            console.print(f"[dim]You can initialize later by running:[/dim] [cyan]{init_cmd_str}[/cyan]")
        console.print()
        raise typer.Exit(code=0)

    return True


def execute_initialization(
    console: Console,
    needs_config: bool,
    needs_inference: bool,
    needs_routing: bool,
    needs_telemetry: bool,
    reset: bool,
    check_inference: bool,
    check_routing: bool,
    backends_toml_path: str,
    telemetry_config_path: str,
):
    """Execute the initialization steps.

    Args:
        console: Rich Console instance for output.
        needs_config: Whether to initialize config files.
        needs_inference: Whether to set up inference backends.
        needs_routing: Whether to set up routing profiles.
        needs_telemetry: Whether to set up telemetry.
        reset: Whether this is a reset operation.
        check_inference: Whether inference was in focus.
        check_routing: Whether routing was in focus.
        backends_toml_path: Path to backends.toml file.
        telemetry_config_path: Path to telemetry config file.

    """
    # Step 1: Initialize config if needed
    if needs_config:
        # Check if backends.toml exists before copying
        backends_existed_before = path_exists(backends_toml_path)

        console.print()
        init_config(reset=reset)

        # If backends.toml was just created (freshly copied), always prompt for backend selection
        backends_exists_now = path_exists(backends_toml_path)
        backends_just_copied = not backends_existed_before and backends_exists_now

        if backends_just_copied or (check_inference and backends_exists_now):
            needs_inference = True

    # Step 2: Set up inference backends if needed
    if needs_inference:
        console.print()
        customize_backends_config()

        # Automatically set up routing after backends (unless routing is the specific focus)
        if not check_routing:
            selected_backend_keys = get_selected_backend_keys(backends_toml_path)
            if selected_backend_keys:
                customize_routing_profile(selected_backend_keys)

    # Step 2.5: Set up routing profile if specifically requested
    if needs_routing:
        console.print()
        selected_backend_keys = get_selected_backend_keys(backends_toml_path)
        if selected_backend_keys:
            customize_routing_profile(selected_backend_keys)
        else:
            console.print("[yellow]⚠ Warning: No backends enabled. Please run 'pipelex init inference' first.[/yellow]")

    # Step 3: Set up telemetry if needed
    if needs_telemetry:
        telemetry_mode = setup_telemetry(console, telemetry_config_path)
        TelemetryManagerAbstract.telemetry_mode_just_set = telemetry_mode

    console.print()


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    reset: bool = False,
    skip_confirmation: bool = False,
    silent: bool = False,
):
    """Initialize Pipelex configuration, inference backends, routing, and telemetry if needed, in a unified flow.

    Args:
        focus: What to initialize - 'config', 'inference', 'routing', 'telemetry', or 'all' (default)
        reset: Whether to reset/overwrite existing files
        skip_confirmation: If True, skip the confirmation prompt (used when called from doctor --fix)
        silent: If True, suppress all output when everything is already configured
    """
    console = Console()
    pipelex_config_dir = config_manager.pipelex_config_dir
    telemetry_config_path = os.path.join(pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME)
    backends_toml_path = os.path.join(pipelex_config_dir, "inference", "backends.toml")
    routing_profiles_toml_path = os.path.join(pipelex_config_dir, "inference", "routing_profiles.toml")

    # Determine what to check based on focus parameter
    check_config = focus in (InitFocus.ALL, InitFocus.CONFIG)
    check_inference = focus in (InitFocus.ALL, InitFocus.INFERENCE)
    check_routing = focus == InitFocus.ROUTING
    check_telemetry = focus in (InitFocus.ALL, InitFocus.TELEMETRY)

    # Check what needs to be initialized
    needs_config, needs_inference, needs_routing, needs_telemetry = determine_needs(
        reset=reset,
        check_config=check_config,
        check_inference=check_inference,
        check_routing=check_routing,
        check_telemetry=check_telemetry,
        backends_toml_path=backends_toml_path,
        routing_profiles_toml_path=routing_profiles_toml_path,
        telemetry_config_path=telemetry_config_path,
    )

    # Track if user already confirmed to avoid double prompting
    user_already_confirmed = False

    # If nothing needs to be done, handle based on focus
    if not needs_config and not needs_inference and not needs_routing and not needs_telemetry:
        # In silent mode, just return without any output
        if silent:
            return

        if handle_already_configured(focus, console, backends_toml_path, routing_profiles_toml_path, telemetry_config_path):
            # User wants to reconfigure
            needs_config, needs_inference, needs_routing, needs_telemetry = update_needs_for_reconfigure(focus)
            user_already_confirmed = True
        else:
            # User doesn't want to reconfigure, exit
            console.print("\n[dim]No changes made.[/dim]")
            console.print()
            return

    try:
        # Show unified initialization prompt (skip if user already confirmed or skip_confirmation is True)
        if not user_already_confirmed and not skip_confirmation:
            confirm_initialization(
                console=console,
                needs_config=needs_config,
                needs_inference=needs_inference,
                needs_routing=needs_routing,
                needs_telemetry=needs_telemetry,
                reset=reset,
                focus=focus,
            )
        else:
            # User already confirmed or skip_confirmation is True, just add a blank line for spacing
            console.print()

        # Execute initialization steps
        execute_initialization(
            console=console,
            needs_config=needs_config,
            needs_inference=needs_inference,
            needs_routing=needs_routing,
            needs_telemetry=needs_telemetry,
            reset=reset,
            check_inference=check_inference,
            check_routing=check_routing,
            backends_toml_path=backends_toml_path,
            telemetry_config_path=telemetry_config_path,
        )

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:
        console.print(f"\n[red]⚠ Warning: Initialization failed: {exc}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
