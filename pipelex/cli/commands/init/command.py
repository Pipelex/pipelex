"""Main command orchestration for the init command."""

import os
import shutil

import typer
from rich.console import Console
from rich.prompt import Confirm

from pipelex.cli.commands.init.backends import customize_backends_config, get_selected_backend_keys
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.routing import customize_routing_profile
from pipelex.cli.commands.init.telemetry import setup_telemetry
from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel, display_already_configured_message
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.misc.file_utils import path_exists


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

        # If reset is True, copy the template file first
        if reset:
            routing_profiles_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "routing_profiles.toml")
            template_routing_path = os.path.join(str(get_kit_configs_dir()), "inference", "routing_profiles.toml")

            if path_exists(template_routing_path):
                shutil.copy2(template_routing_path, routing_profiles_toml_path)
                console.print("✅ Reset routing_profiles.toml from template")

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
