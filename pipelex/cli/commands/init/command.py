"""Main command orchestration for the init command."""

import os
import shutil
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm

from pipelex.cli.commands.init.backends import (
    customize_backends_config,
    disable_gateway_backend,
    get_selected_backend_keys,
)
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.credentials import prompt_credentials
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
from pipelex.cogt.models.deck_manifest import compute_kit_manifest, write_manifest
from pipelex.hub import get_console
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import BACKENDS_FILE_NAME, INFERENCE_DIR_NAME, config_manager
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError
from pipelex.system.pipelex_service.pipelex_service_agreement import update_service_terms_acceptance
from pipelex.system.pipelex_service.pipelex_service_config import (
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME
from pipelex.tools.misc.file_utils import path_exists


class CachePrimingResult(BaseModel):
    """Outcome of an attempt to prime the on-disk remote-config cache.

    ``primed`` is ``True`` only when a fresh fetch succeeded and the cache was written.
    ``error_message`` is populated only when the fetch was attempted but failed (offline at init
    time); ``None`` means priming was skipped (gateway disabled or terms not accepted) or that
    it succeeded.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    primed: bool
    error_message: str | None = None


def attempt_prime_remote_config_cache(target_config_dir: Path | None = None) -> CachePrimingResult:
    """Prime the on-disk remote-config cache so later offline runs can fall back to it.

    Pure-logic variant: no I/O on the way out, so both the interactive (`pipelex init`) and
    machine (`pipelex-agent init`) surfaces can decide how to surface failure (Rich warning vs
    structured JSON field).

    Skipped (``primed=False, error_message=None``) when:
    - the gateway is disabled in ``backends.toml`` (BYOK has nothing to cache), or
    - gateway terms have not been accepted (we cannot fetch without consent).

    Always passes ``require_fresh=True`` to the fetcher: priming's only job is to write a fresh
    cache, so silently accepting an existing cached fallback would be a misleading success. When
    the network is unreachable and only a stale cache exists, the fetcher raises
    ``RemoteConfigUnavailableError`` and we surface that as ``error_message`` — the stale cache
    on disk is left intact so subsequent offline dry-runs can still fall back to it.

    ``RemoteConfigValidationError`` is intentionally NOT caught: a server-side schema break is a
    real bug (we control the back-office) and should surface loudly rather than be hidden by the
    priming step.

    Args:
        target_config_dir: When set, read the ``backends.toml`` *at that directory* to decide
            whether the gateway is enabled. ``pipelex init`` and ``pipelex init --local``
            target different ``.pipelex/`` directories — using the layered/project-preferred
            config here would let priming branch on the wrong file. ``None`` (default) falls
            back to the layered path. The terms-acceptance check always reads the *global*
            ``pipelex_service.toml`` by design.
    """
    if target_config_dir is not None:
        backends_file_path = target_config_dir / INFERENCE_DIR_NAME / BACKENDS_FILE_NAME
    else:
        backends_file_path = None
    if not is_pipelex_gateway_enabled(backends_file_path=backends_file_path):
        return CachePrimingResult(primed=False)

    service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)
    if service_config is None or not service_config.agreement.terms_accepted:
        return CachePrimingResult(primed=False)

    try:
        RemoteConfigFetcher.fetch_remote_config(require_fresh=True)
    except RemoteConfigUnavailableError as exc:
        return CachePrimingResult(primed=False, error_message=str(exc))
    return CachePrimingResult(primed=True)


def prime_remote_config_cache(console: Console, target_config_dir: Path | None = None) -> None:
    """Interactive-surface wrapper around :func:`attempt_prime_remote_config_cache`.

    Prints a yellow warning to the console when a fetch was attempted and failed; otherwise
    silent. Used by ``pipelex init`` so the user knows priming didn't happen and how to retry.

    ``target_config_dir`` is forwarded so the gateway-enabled check inspects the directory
    being initialized rather than the layered config (see ``attempt_prime_remote_config_cache``).
    """
    result = attempt_prime_remote_config_cache(target_config_dir=target_config_dir)
    if result.error_message is not None:
        console.print(f"[yellow]⚠ Could not prime remote config cache: {escape(result.error_message)}[/yellow]")
        console.print("[dim]Re-run 'pipelex init' while online to prime the cache for offline dry-runs.[/dim]")


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

    # Gateway is enabled - check if terms are already accepted (always global)
    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)
    if pipelex_service_config is not None and pipelex_service_config.agreement.terms_accepted:
        return

    # Gateway is enabled but terms not accepted - prompt user
    gateway_accepted = prompt_gateway_acceptance(console)

    config_manager.global_config_dir.mkdir(parents=True, exist_ok=True)
    if gateway_accepted:
        display_gateway_accepted_message(console)
        update_service_terms_acceptance(accepted=True, config_dir=config_manager.global_config_dir)
    else:
        display_gateway_declined_message(console)
        update_service_terms_acceptance(accepted=False, config_dir=config_manager.global_config_dir)
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
    nb_missing_config_files = (
        init_config(reset=False, dry_run=True, target_dir=str(target_config_dir) if target_config_dir else None) if check_config else 0
    )
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
    console.print(build_initialization_panel(needs_config, needs_inference, needs_routing, needs_telemetry, reset, check_credentials))

    if not Confirm.ask("[bold]Continue with initialization?[/bold]", default=True):
        console.print("\n[yellow]Initialization cancelled.[/yellow]")
        if needs_config or needs_inference or needs_routing or needs_telemetry:
            match focus:
                case InitFocus.AGREEMENT:
                    init_cmd_str = "pipelex init agreement"
                case InitFocus.ALL:
                    init_cmd_str = "pipelex init"
                case InitFocus.CONFIG | InitFocus.CREDENTIALS | InitFocus.INFERENCE | InitFocus.ROUTING | InitFocus.TELEMETRY:
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
    check_credentials: bool,
    reset: bool,
    check_inference: bool,
    check_routing: bool,
    backends_toml_path: str,
    telemetry_config_path: str,
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
        backends_existed_before = path_exists(backends_toml_path)

        console.print()
        init_config(reset=reset, target_dir=str(target_config_dir) if target_config_dir else None)

        # init_config skips the inference/ directory (handled independently by the inference step).
        # Detect first-time setup: if backends.toml didn't exist before, inference needs to be set up.
        backends_exists_now = path_exists(backends_toml_path)

        if not backends_existed_before or (check_inference and backends_exists_now):
            needs_inference = True

        # If we're NOT going to run customize_backends_config (which handles gateway terms),
        # we need to check if gateway is enabled and terms not accepted
        if not needs_inference and backends_existed_before:
            _check_gateway_terms_if_needed(console, backends_toml_path)

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
            Path(backends_toml_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_backends_path, backends_toml_path)

            # Reset all individual backend files in backends/ directory
            template_backends_dir = template_inference_dir / "backends"
            target_backends_dir = target_inference_dir / "backends"
            target_backends_dir.mkdir(parents=True, exist_ok=True)
            for backend_file in os.listdir(template_backends_dir):
                if backend_file.endswith((".toml", ".md")):
                    src_path = template_backends_dir / backend_file
                    dst_path = target_backends_dir / backend_file
                    shutil.copy2(src_path, dst_path)

            # Reset deck/ directory files (model deck configurations)
            template_deck_dir = template_inference_dir / "deck"
            target_deck_dir = target_inference_dir / "deck"
            target_deck_dir.mkdir(parents=True, exist_ok=True)
            for deck_file in os.listdir(template_deck_dir):
                if deck_file.endswith(".toml"):
                    src_path = template_deck_dir / deck_file
                    dst_path = target_deck_dir / deck_file
                    shutil.copy2(src_path, dst_path)

            # Stamp the deck manifest so future updates can detect drift and
            # `pipelex update` knows the exact kit version this install came from.
            write_manifest(target_deck_dir, compute_kit_manifest())

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
        prompt_credentials(console, backends_toml_path)

    # Step 3: Set up routing profile if specifically requested
    if needs_routing:
        console.print()

        # If reset is True, copy the template file first
        if reset:
            effective_config_dir_for_routing = target_config_dir or config_manager.pipelex_config_dir
            routing_profiles_toml_path = str(effective_config_dir_for_routing / "inference" / "routing_profiles.toml")
            template_routing_path = Path(str(get_kit_configs_dir())) / "inference" / "routing_profiles.toml"
            Path(routing_profiles_toml_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_routing_path, routing_profiles_toml_path)
            console.print("✅ Reset routing_profiles.toml from template")

        selected_backend_keys = get_selected_backend_keys(backends_toml_path)
        if selected_backend_keys:
            customize_routing_profile(selected_backend_keys, target_config_dir=target_config_dir)
        else:
            console.print("[yellow]⚠ Warning: No backends enabled. Please run 'pipelex init inference' first.[/yellow]")

    # Step 4: Set up telemetry if needed
    if needs_telemetry:
        setup_telemetry(console, telemetry_config_path, for_project=for_project)

    # Step 5: Prime the remote-config cache so dry-runs and validate can fall back offline.
    # No-op when gateway is disabled or terms have not been accepted. We forward
    # ``target_config_dir`` so the gateway-enabled check inspects the directory we just
    # initialized (matters for ``--local`` vs default init).
    prime_remote_config_cache(console, target_config_dir=target_config_dir)

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

    # Check current terms acceptance status (always global)
    pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)

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
        update_service_terms_acceptance(accepted=True, config_dir=config_manager.global_config_dir)
    else:
        display_gateway_declined_message(console)
        update_service_terms_acceptance(accepted=False, config_dir=config_manager.global_config_dir)
        # Disable the gateway since terms were declined
        backends_toml_path = str(config_manager.pipelex_config_dir / "inference" / "backends.toml")
        if path_exists(backends_toml_path):
            disable_gateway_backend(backends_toml_path)

    console.print()


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    skip_confirmation: bool = False,
    local: bool = False,
):
    """Initialize Pipelex configuration, inference backends, credentials, routing, and telemetry.

    Note: Config updates are not yet supported. This command always performs a full reset
    of the configuration, overwriting any existing files.

    Args:
        focus: What to initialize - 'all', 'agreement', 'config', 'credentials', 'inference', 'routing', or 'telemetry'
        skip_confirmation: If True, skip the confirmation prompt (used when called from doctor --fix)
        local: If True, create project-level .pipelex/ at the detected project root. Otherwise, create global ~/.pipelex/.
    """
    console = get_console()

    # Handle agreement-only flow separately (no reset needed)
    if focus == InitFocus.AGREEMENT:
        _init_agreement(console)
        return

    # Handle credentials-only flow separately (no reset needed)
    if focus == InitFocus.CREDENTIALS:
        backends_toml_path = str(config_manager.pipelex_config_dir / "inference" / "backends.toml")
        if not path_exists(backends_toml_path):
            console.print()
            console.print("[yellow]No backends.toml found. Please run 'pipelex init' first.[/yellow]")
            console.print()
            return
        prompt_credentials(console, backends_toml_path)
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
    telemetry_config_path = str(pipelex_config_dir / TELEMETRY_CONFIG_FILE_NAME)
    backends_toml_path = str(pipelex_config_dir / "inference" / "backends.toml")
    routing_profiles_toml_path = str(pipelex_config_dir / "inference" / "routing_profiles.toml")

    # Determine what to check based on focus parameter
    check_config = focus in {InitFocus.ALL, InitFocus.CONFIG}
    check_credentials = focus in {InitFocus.ALL, InitFocus.CONFIG, InitFocus.INFERENCE}
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
    except Exception as exc:
        console.print(f"\n[red]⚠ Warning: Initialization failed: {escape(str(exc))}[/red]", style="bold")
        if needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
