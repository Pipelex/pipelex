"""Main command orchestration for the init command."""

import os
import shutil

import typer
from rich.console import Console
from rich.prompt import Confirm

from pipelex.cli.commands.init.backends import (
    customize_backends_config,
    disable_gateway_backend,
    get_selected_backend_keys,
)
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.routing import customize_routing_profile
from pipelex.cli.commands.init.telemetry import setup_telemetry
from pipelex.cli.commands.init.ui.gateway_ui import (
    build_gateway_terms_panel,
    display_gateway_accepted_message,
    display_gateway_declined_message,
    prompt_gateway_acceptance,
)
from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.hub import get_console
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.pipelex_service.pipelex_service_agreement import update_service_terms_acceptance
from pipelex.system.pipelex_service.pipelex_service_config import (
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME
from pipelex.tools.misc.file_utils import path_exists


def _check_gateway_terms_if_needed(console: Console, backends_toml_path: str) -> None:
    """Check if gateway is enabled and terms not yet accepted, then prompt for acceptance.

    This is called after init_config() to ensure users who have gateway enabled
    in their existing backends.toml are prompted to accept terms when pipelex_service.toml
    is first created.

    Args:
        console: Rich Console instance for user interaction.
        backends_toml_path: Path to backends.toml file.
    """
    # Check if backends.toml exists and gateway is enabled
    if not path_exists(backends_toml_path):
        return

    selected_backend_keys = get_selected_backend_keys(backends_toml_path)
    if PipelexBackend.GATEWAY not in selected_backend_keys:
        return

    # Gateway is enabled - check if terms are already accepted
    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.pipelex_config_dir)
    if pipelex_service_config is not None and pipelex_service_config.agreement.terms_accepted:
        return

    # Gateway is enabled but terms not accepted - prompt user
    gateway_accepted = prompt_gateway_acceptance(console)

    if gateway_accepted:
        display_gateway_accepted_message(console)
        update_service_terms_acceptance(accepted=True)
    else:
        display_gateway_declined_message(console)
        update_service_terms_acceptance(accepted=False)
        # Actually disable the gateway in backends.toml
        disable_gateway_backend(backends_toml_path)


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
                case InitFocus.AGREEMENT:
                    init_cmd_str = "pipelex init agreement"
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
    is_first_time_backends_setup: bool,
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
        is_first_time_backends_setup: Whether backends.toml didn't exist before this run.

    """
    # Track if backends were just copied during config initialization
    backends_just_copied_during_config = False

    # Step 1: Initialize config if needed
    if needs_config:
        # Check if backends.toml exists before copying
        backends_existed_before = path_exists(backends_toml_path)

        console.print()
        init_config(reset=reset)

        # If backends.toml was just created (freshly copied), always prompt for backend selection
        backends_exists_now = path_exists(backends_toml_path)
        backends_just_copied_during_config = not backends_existed_before and backends_exists_now

        if backends_just_copied_during_config or (check_inference and backends_exists_now):
            needs_inference = True

        # If we're NOT going to run customize_backends_config (which handles gateway terms),
        # we need to check if gateway is enabled and terms not accepted
        if not needs_inference and backends_existed_before:
            _check_gateway_terms_if_needed(console, backends_toml_path)

    # Determine if this is truly a first-time setup (either tracked from before or just copied now)
    first_time_setup = is_first_time_backends_setup or backends_just_copied_during_config

    # Step 2: Set up inference backends if needed
    if needs_inference:
        console.print()

        # If reset is True and we didn't already copy via config init, copy the template files
        if reset and not backends_just_copied_during_config:
            template_inference_dir = os.path.join(str(get_kit_configs_dir()), "inference")
            target_inference_dir = os.path.join(config_manager.pipelex_config_dir, "inference")

            # Reset backends.toml
            template_backends_path = os.path.join(template_inference_dir, "backends.toml")
            os.makedirs(os.path.dirname(backends_toml_path), exist_ok=True)
            shutil.copy2(template_backends_path, backends_toml_path)
            console.print("✅ Reset backends.toml from template")

            # Reset all individual backend files in backends/ directory
            template_backends_dir = os.path.join(template_inference_dir, "backends")
            target_backends_dir = os.path.join(target_inference_dir, "backends")
            os.makedirs(target_backends_dir, exist_ok=True)
            reset_backend_files: list[str] = []
            for backend_file in os.listdir(template_backends_dir):
                if backend_file.endswith(".toml"):
                    src_path = os.path.join(template_backends_dir, backend_file)
                    dst_path = os.path.join(target_backends_dir, backend_file)
                    shutil.copy2(src_path, dst_path)
                    reset_backend_files.append(backend_file)
            if reset_backend_files:
                console.print(f"✅ Reset {len(reset_backend_files)} backend config files from template")

            # Reset deck/ directory files (model deck configurations)
            template_deck_dir = os.path.join(template_inference_dir, "deck")
            target_deck_dir = os.path.join(target_inference_dir, "deck")
            os.makedirs(target_deck_dir, exist_ok=True)
            reset_deck_files: list[str] = []
            for deck_file in os.listdir(template_deck_dir):
                if deck_file.endswith(".toml"):
                    src_path = os.path.join(template_deck_dir, deck_file)
                    dst_path = os.path.join(target_deck_dir, deck_file)
                    shutil.copy2(src_path, dst_path)
                    reset_deck_files.append(deck_file)
            if reset_deck_files:
                console.print(f"✅ Reset {len(reset_deck_files)} model deck config files from template")

            first_time_setup = True  # Treat as first-time setup since we just replaced the files

        customize_backends_config(is_first_time_setup=first_time_setup)

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
            shutil.copy2(template_routing_path, routing_profiles_toml_path)
            console.print("✅ Reset routing_profiles.toml from template")

        selected_backend_keys = get_selected_backend_keys(backends_toml_path)
        if selected_backend_keys:
            customize_routing_profile(selected_backend_keys)
        else:
            console.print("[yellow]⚠ Warning: No backends enabled. Please run 'pipelex init inference' first.[/yellow]")

    # Step 3: Set up telemetry if needed
    if needs_telemetry:
        setup_telemetry(console, telemetry_config_path)

    console.print()


def _init_agreement(console: Console) -> None:
    """Handle the agreement-only initialization flow.

    This prompts the user to accept Pipelex Gateway terms without resetting any configuration.
    If gateway is not enabled, it informs the user that no action is needed.

    Args:
        console: Rich Console instance for user interaction.
    """
    # Check if gateway is even enabled
    if not is_pipelex_gateway_enabled():
        console.print()
        console.print("[green]✓ Pipelex Gateway is not enabled.[/green]")
        console.print("[dim]No terms acceptance is required.[/dim]")
        console.print()
        return

    # Check current terms acceptance status
    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.pipelex_config_dir)

    if pipelex_service_config is not None and pipelex_service_config.agreement.terms_accepted:
        console.print()
        console.print("[green]✓ Pipelex Gateway terms have already been accepted.[/green]")
        console.print()
        return

    # Show the terms panel and prompt for acceptance
    console.print()
    console.print(build_gateway_terms_panel())
    console.print()

    accepted = Confirm.ask(
        "[bold]Do you accept the Pipelex Gateway terms of service?[/bold]",
        console=console,
        default=True,
    )

    if accepted:
        display_gateway_accepted_message(console)
        update_service_terms_acceptance(accepted=True)
    else:
        display_gateway_declined_message(console)
        update_service_terms_acceptance(accepted=False)
        # Disable the gateway since terms were declined
        backends_toml_path = os.path.join(config_manager.pipelex_config_dir, "inference", "backends.toml")
        if path_exists(backends_toml_path):
            disable_gateway_backend(backends_toml_path)

    console.print()


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    skip_confirmation: bool = False,
):
    """Initialize Pipelex configuration, inference backends, routing, and telemetry.

    Note: Config updates are not yet supported. This command always performs a full reset
    of the configuration, overwriting any existing files.

    Args:
        focus: What to initialize - 'agreement', 'config', 'inference', 'routing', 'telemetry', or 'all' (default)
        skip_confirmation: If True, skip the confirmation prompt (used when called from doctor --fix)
    """
    console = get_console()

    # Handle agreement-only flow separately (no reset needed)
    if focus == InitFocus.AGREEMENT:
        _init_agreement(console)
        return

    # Config updates are not yet supported - always reset
    reset = True
    pipelex_config_dir = config_manager.pipelex_config_dir
    telemetry_config_path = os.path.join(pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME)
    backends_toml_path = os.path.join(pipelex_config_dir, "inference", "backends.toml")
    routing_profiles_toml_path = os.path.join(pipelex_config_dir, "inference", "routing_profiles.toml")

    # Determine what to check based on focus parameter
    check_config = focus in {InitFocus.ALL, InitFocus.CONFIG}
    check_inference = focus in {InitFocus.ALL, InitFocus.INFERENCE}
    check_routing = focus == InitFocus.ROUTING
    check_telemetry = focus in {InitFocus.ALL, InitFocus.TELEMETRY}

    # Track if backends.toml existed before we start
    is_first_time_backends_setup = not path_exists(backends_toml_path)

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

    # Show info message if config already exists
    if not is_first_time_backends_setup and not skip_confirmation:
        console.print()
        console.print("[dim]ℹ Config update requires running a full reset.[/dim]")

    try:
        # Show unified initialization prompt (skip if skip_confirmation is True)
        if not skip_confirmation:
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
            # skip_confirmation is True, just add a blank line for spacing
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
            is_first_time_backends_setup=is_first_time_backends_setup,
        )

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:
        console.print(f"\n[red]⚠ Warning: Initialization failed: {exc}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
