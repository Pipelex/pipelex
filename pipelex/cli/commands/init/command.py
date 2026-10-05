"""Main command orchestration for the init command."""

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm

from pipelex.cli.commands.init.backends import (
    customize_backends_config,
    get_selected_backend_keys,
)
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.credentials import prompt_credentials
from pipelex.cli.commands.init.routing import customize_routing_profile
from pipelex.cli.commands.init.telemetry import setup_telemetry
from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.models.deck_manifest import stamp_kit_manifests
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME


def determine_needs(
    *,
    reset: bool,
    check_config: bool,
    check_inference: bool,
    check_routing: bool,
    check_telemetry: bool,
    backends_toml_path: Path,
    routing_profiles_toml_path: Path,
    telemetry_config_path: Path,
    target_config_dir: Path | None = None,
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
        target_config_dir: Explicit target .pipelex directory. If None, uses config_manager.pipelex_config_dir.

    Returns:
        Tuple of (needs_config, needs_inference, needs_routing, needs_telemetry) booleans.
    """
    nb_missing_config_files = init_config(reset=False, dry_run=True, target_dir=target_config_dir) if check_config else 0
    needs_config = check_config and (nb_missing_config_files > 0 or reset)
    needs_inference = check_inference and (not backends_toml_path.exists() or reset)
    needs_routing = check_routing and (not routing_profiles_toml_path.exists() or reset)
    needs_telemetry = check_telemetry and (not telemetry_config_path.exists() or reset)

    return needs_config, needs_inference, needs_routing, needs_telemetry


def confirm_initialization(
    *,
    console: Console,
    needs_config: bool,
    needs_inference: bool,
    needs_routing: bool,
    needs_telemetry: bool,
    check_credentials: bool,
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
        check_credentials: Whether credential prompting will happen.
        reset: Whether this is a reset operation.
        focus: The initialization focus area.

    Returns:
        True if user confirms, False otherwise.

    Raises:
        typer.Exit: If user cancels initialization.
    """
    console.print()
    console.print(
        build_initialization_panel(
            needs_config=needs_config,
            needs_inference=needs_inference,
            needs_routing=needs_routing,
            needs_telemetry=needs_telemetry,
            reset=reset,
            check_credentials=check_credentials,
        )
    )

    if not Confirm.ask("[bold]Continue with initialization?[/bold]", default=True):
        console.print("\n[yellow]Initialization cancelled.[/yellow]")
        if needs_config or needs_inference or needs_routing or needs_telemetry:
            match focus:
                case InitFocus.ALL:
                    init_cmd_str = "pipelex init"
                case InitFocus.CONFIG | InitFocus.CREDENTIALS | InitFocus.INFERENCE | InitFocus.ROUTING | InitFocus.TELEMETRY:
                    init_cmd_str = f"pipelex init {focus}"
            console.print(f"[dim]You can initialize later by running:[/dim] [cyan]{init_cmd_str}[/cyan]")
        console.print()
        raise typer.Exit(code=0)

    return True


def execute_initialization(
    *,
    console: Console,
    needs_config: bool,
    needs_inference: bool,
    needs_routing: bool,
    needs_telemetry: bool,
    check_credentials: bool,
    reset: bool,
    check_inference: bool,
    check_routing: bool,
    backends_toml_path: Path,
    telemetry_config_path: Path,
    is_first_time_backends_setup: bool,
    target_config_dir: Path | None = None,
    for_project: bool = False,
):
    """Execute the initialization steps.

    Args:
        console: Rich Console instance for output.
        needs_config: Whether to initialize config files.
        needs_inference: Whether to set up inference backends.
        needs_routing: Whether to set up routing profiles.
        needs_telemetry: Whether to set up telemetry.
        check_credentials: Whether to prompt for missing credentials.
        reset: Whether this is a reset operation.
        check_inference: Whether inference was in focus.
        check_routing: Whether routing was in focus.
        backends_toml_path: Path to backends.toml file.
        telemetry_config_path: Path to telemetry config file.
        is_first_time_backends_setup: Whether backends.toml didn't exist before this run.
        target_config_dir: Explicit target .pipelex directory. If None, uses config_manager.pipelex_config_dir.
        for_project: True when initializing a project's .pipelex/; False when initializing
            the global ~/.pipelex/. Selects which telemetry template gets copied.

    """
    # Step 1: Initialize config if needed
    if needs_config:
        # Check if backends.toml exists before copying
        backends_existed_before = backends_toml_path.exists()

        console.print()
        init_config(reset=reset, target_dir=target_config_dir)

        # init_config skips the inference/ directory (handled independently by the inference step).
        # Detect first-time setup: if backends.toml didn't exist before, inference needs to be set up.
        backends_exists_now = backends_toml_path.exists()

        if not backends_existed_before or (check_inference and backends_exists_now):
            needs_inference = True

    # Determine if this is truly a first-time setup
    first_time_setup = is_first_time_backends_setup

    # Step 2: Set up inference backends if needed
    if needs_inference:
        console.print()

        # Copy the inference template files when resetting (init_config skips inference/)
        if reset:
            template_inference_dir = Path(str(get_kit_configs_dir())) / "inference"
            effective_config_dir = target_config_dir or config_manager.pipelex_config_dir
            target_inference_dir = effective_config_dir / "inference"

            # Reset backends.toml
            template_backends_path = template_inference_dir / "backends.toml"
            backends_toml_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_backends_path, backends_toml_path)

            # Reset all individual backend files in backends/ directory
            template_backends_dir = template_inference_dir / "backends"
            target_backends_dir = target_inference_dir / "backends"
            target_backends_dir.mkdir(parents=True, exist_ok=True)
            for backend_file in template_backends_dir.iterdir():
                if backend_file.suffix in {".toml", ".md"}:
                    dst_path = target_backends_dir / backend_file.name
                    shutil.copy2(backend_file, dst_path)

            # Reset deck/ directory files (model deck configurations)
            template_deck_dir = template_inference_dir / "deck"
            target_deck_dir = target_inference_dir / "deck"
            target_deck_dir.mkdir(parents=True, exist_ok=True)
            for deck_file in template_deck_dir.iterdir():
                if deck_file.suffix == ".toml":
                    dst_path = target_deck_dir / deck_file.name
                    shutil.copy2(deck_file, dst_path)

            # Stamp the kit manifests of the deck and of backends/internal.toml so future updates can
            # detect drift and `pipelex update` knows the exact kit version this install came from.
            stamp_kit_manifests(inference_dir=target_inference_dir)

            # Reset routing_profiles.toml
            template_routing_path = template_inference_dir / "routing_profiles.toml"
            target_routing_path = target_inference_dir / "routing_profiles.toml"
            if template_routing_path.exists():
                shutil.copy2(template_routing_path, target_routing_path)
                console.print("✅ Reset routing_profiles.toml from template")

            first_time_setup = True  # Treat as first-time setup since we just replaced the files

        customize_backends_config(is_first_time_setup=first_time_setup, target_config_dir=target_config_dir)

        # Automatically set up routing after backends (unless routing is the specific focus)
        if not check_routing:
            selected_backend_keys = get_selected_backend_keys(backends_toml_path)
            if selected_backend_keys:
                customize_routing_profile(selected_backend_keys, target_config_dir=target_config_dir)

    # Step 2.5: Prompt for missing credentials
    if check_credentials:
        prompt_credentials(console=console, backends_toml_path=backends_toml_path)

    # Step 3: Set up routing profile if specifically requested
    if needs_routing:
        console.print()

        # If reset is True, copy the template file first
        if reset:
            effective_config_dir_for_routing = target_config_dir or config_manager.pipelex_config_dir
            routing_profiles_toml_path = effective_config_dir_for_routing / "inference" / "routing_profiles.toml"
            template_routing_path = Path(str(get_kit_configs_dir())) / "inference" / "routing_profiles.toml"
            routing_profiles_toml_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_routing_path, routing_profiles_toml_path)
            console.print("✅ Reset routing_profiles.toml from template")

        selected_backend_keys = get_selected_backend_keys(backends_toml_path)
        if selected_backend_keys:
            customize_routing_profile(selected_backend_keys, target_config_dir=target_config_dir)
        else:
            console.print("[yellow]⚠ Warning: No backends enabled. Please run 'pipelex init inference' first.[/yellow]")

    # Step 4: Set up telemetry if needed
    if needs_telemetry:
        setup_telemetry(console=console, telemetry_config_path=telemetry_config_path, for_project=for_project)

    console.print()


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    *,
    skip_confirmation: bool = False,
    local: bool = False,
):
    """Initialize Pipelex configuration, inference backends, credentials, routing, and telemetry.

    Note: Config updates are not yet supported. This command always performs a full reset
    of the configuration, overwriting any existing files.

    Args:
        focus: What to initialize - 'all', 'config', 'credentials', 'inference', 'routing', or 'telemetry'
        skip_confirmation: If True, skip the confirmation prompt (used when called from doctor --fix)
        local: If True, create project-level .pipelex/ at the detected project root. Otherwise, create global ~/.pipelex/.
    """
    console = get_console()

    # Handle credentials-only flow separately (no reset needed)
    if focus == InitFocus.CREDENTIALS:
        backends_toml_path = config_manager.pipelex_config_dir / "inference" / "backends.toml"
        if not backends_toml_path.exists():
            console.print()
            console.print("[yellow]No backends.toml found. Please run 'pipelex init' first.[/yellow]")
            console.print()
            return
        prompt_credentials(console=console, backends_toml_path=backends_toml_path)
        console.print()
        return

    # Config updates are not yet supported - always reset
    reset = True

    # Determine target directory
    if local:
        # --local: create at project root, fall back to CWD
        project_root = config_manager.project_root
        if project_root is not None:
            target_config_dir = project_root / ".pipelex"
        else:
            target_config_dir = Path.cwd() / ".pipelex"
    else:
        # Default: create global config at ~/.pipelex/
        target_config_dir = config_manager.global_config_dir
    console.print(f"[dim]Target directory: {target_config_dir}[/dim]")

    pipelex_config_dir = target_config_dir
    telemetry_config_path = pipelex_config_dir / TELEMETRY_CONFIG_FILE_NAME
    backends_toml_path = pipelex_config_dir / "inference" / "backends.toml"
    routing_profiles_toml_path = pipelex_config_dir / "inference" / "routing_profiles.toml"

    # Determine what to check based on focus parameter
    check_config = focus in {InitFocus.ALL, InitFocus.CONFIG}
    check_credentials = focus in {InitFocus.ALL, InitFocus.CONFIG, InitFocus.INFERENCE}
    check_inference = focus in {InitFocus.ALL, InitFocus.INFERENCE}
    check_routing = focus == InitFocus.ROUTING
    check_telemetry = focus in {InitFocus.ALL, InitFocus.TELEMETRY}

    # Track if backends.toml existed before we start
    is_first_time_backends_setup = not backends_toml_path.exists()

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
        target_config_dir=pipelex_config_dir,
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
                check_credentials=check_credentials,
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
            check_credentials=check_credentials,
            reset=reset,
            check_inference=check_inference,
            check_routing=check_routing,
            backends_toml_path=backends_toml_path,
            telemetry_config_path=telemetry_config_path,
            is_first_time_backends_setup=is_first_time_backends_setup,
            target_config_dir=pipelex_config_dir,
            for_project=local,
        )

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:  # ruff: ignore[blind-except]
        # Command-level boundary: any unexpected init failure is reported as a warning and the command returns without crashing.
        console.print(f"\n[red]⚠ Warning: Initialization failed: {escape(str(exc))}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
