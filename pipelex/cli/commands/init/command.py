"""Main command orchestration for the init command.

`init_cmd` runs in three stages:

1. **Inspect** (`inspect_initialization`): read what is on disk and what the focus asks for, and decide which steps
   are needed. It asks nothing and writes nothing. It also finds what a former release that ran on the Pipelex Gateway
   or Pipelex Manifold left in the configuration directories a boot reads, read together as the boot merges them, and
   whether it stops this machine's boot, which is the boot's own check over the files it merges.
2. **Choose** (`choose_initialization`): first, when the inspection found what a former release left and someone is
   there to answer, say so and offer the cleanup `pipelex migrate` runs, then run it on a yes; then the
   confirmation, then where runs execute, the hosted Pipelex API or this machine. An unattended run (`pipelex doctor
   --fix`) never runs the cleanup: the doctor asks about it itself.
3. **Execute** (`execute_initialization`): write the files and run the steps the choices call for. Only the local
   path's own steps (backends, routing, credentials) and the hosted path's sign-in ask anything more.
"""

import shutil
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm

from pipelex import log
from pipelex.cli.commands.init.backends import (
    customize_backends_config,
    get_selected_backend_keys,
)
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.credentials import prompt_credentials
from pipelex.cli.commands.init.ide_extension import suggest_extension_install_if_needed
from pipelex.cli.commands.init.routing import customize_routing_profile
from pipelex.cli.commands.init.setup_path import (
    DEFAULT_SETUP_PATH,
    SetupPath,
    apply_setup_path_setting,
    ensure_pipelex_api_key,
    read_run_execution,
    write_run_execution,
)
from pipelex.cli.commands.init.telemetry import setup_telemetry
from pipelex.cli.commands.init.ui.general_ui import build_initialization_panel
from pipelex.cli.commands.init.ui.setup_path_ui import prompt_setup_path
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND
from pipelex.cli.commands.migrate_cmd import apply_former_release_cleanup
from pipelex.cogt.models.deck_manifest import stamp_kit_manifests
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.migration.former_release import (
    FormerReleaseFinding,
    FormerReleaseFindings,
    detect_former_release_across,
    former_release_boot_blockers,
    kit_default_routing_profile_name,
)
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME

#: The focuses whose run asks where runs execute when it sets up inference: the full setup, and a first setup reached
#: through `config`. `inference` configures this machine's backends on purpose and leaves the setting as it is.
SETUP_PATH_FOCUSES: frozenset[InitFocus] = frozenset({InitFocus.ALL, InitFocus.CONFIG})


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


class InitInspection(BaseModel):
    """What an init run found on disk and what it will do, decided before anything is asked or written."""

    model_config = ConfigDict(frozen=True)

    focus: InitFocus
    target_config_dir: Path
    for_project: bool
    reset: bool
    backends_toml_path: Path
    routing_profiles_toml_path: Path
    telemetry_config_path: Path
    pipelex_toml_path: Path
    #: Whether the target `pipelex.toml` exists: a home without one is brand new.
    pipelex_toml_exists: bool
    is_first_time_backends_setup: bool
    #: The `[run] execution` the target `pipelex.toml` sets now, kept across a reset that does not ask again.
    configured_execution: RunExecution | None
    check_credentials: bool
    check_inference: bool
    check_routing: bool
    needs_config: bool
    needs_inference: bool
    needs_routing: bool
    needs_telemetry: bool
    #: The configuration directories a boot reads, the home's then the project's, which the former-release cleanup runs over.
    former_release_config_dirs: list[Path]
    #: What a former release left in each of them, read as the boot merges them; empty when nothing.
    former_release_findings: list[FormerReleaseFindings]
    #: What of it stops this machine's boot, read off the files that boot merges; empty when the boot starts.
    former_release_boot_blockers: list[FormerReleaseFinding]

    @property
    def asks_setup_path(self) -> bool:
        """Whether this run decides where runs execute: when it sets up inference for the full setup, or for a first one."""
        return self.needs_inference and self.focus in SETUP_PATH_FOCUSES

    @property
    def kept_execution(self) -> RunExecution | None:
        """The setting to write back after the configuration files are reset without asking where runs execute."""
        if self.needs_config and not self.asks_setup_path:
            return self.configured_execution
        return None

    @property
    def keeps_hosted_runs(self) -> bool:
        """Whether a reset that does not ask again keeps runs on the hosted Pipelex API, so asks for no provider key."""
        return self.kept_execution is not None and self.kept_execution.is_hosted

    @property
    def unattended_setup_path(self) -> SetupPath | None:
        """The path taken when nobody is asked (`pipelex doctor --fix`).

        None when this run does not decide where runs execute. Otherwise installing missing files never moves runs off
        this machine: the target's `[run] execution` is kept when it sets one, a `pipelex.toml` that sets none, such as
        one written before `[run]` existed, runs locally as the package default says and stays local, and the hosted
        default is taken only for a brand-new home, with no `pipelex.toml` yet.
        """
        if not self.asks_setup_path:
            return None
        if self.configured_execution is not None:
            return SetupPath.from_run_execution(execution=self.configured_execution)
        if self.pipelex_toml_exists:
            return SetupPath.LOCAL
        return DEFAULT_SETUP_PATH


class InitChoices(BaseModel):
    """What the person chose, or what was taken for them when nobody was asked."""

    model_config = ConfigDict(frozen=True)

    #: Where runs execute, when this run decides it; `None` when it does not.
    setup_path: SetupPath | None
    #: Whether someone answers prompts: `False` for `pipelex doctor --fix`.
    interactive: bool


def inspect_initialization(*, focus: InitFocus, local: bool) -> InitInspection:
    """Stage 1: find the target directory, read what is there, and decide which steps the focus needs.

    Args:
        focus: What to initialize.
        local: Target the project's `.pipelex/` at the detected project root instead of the home configuration directory.

    Returns:
        The inspection the later stages work from. Nothing is asked or written.
    """
    # Config updates are not yet supported - always reset
    reset = True

    if local:
        # --local: create at project root, fall back to CWD
        project_root = config_manager.project_root
        if project_root is not None:
            target_config_dir = project_root / ".pipelex"
        else:
            target_config_dir = Path.cwd() / ".pipelex"
    else:
        # Default: create the global config in the home configuration directory
        target_config_dir = config_manager.global_config_dir

    telemetry_config_path = target_config_dir / TELEMETRY_CONFIG_FILE_NAME
    backends_toml_path = target_config_dir / "inference" / "backends.toml"
    routing_profiles_toml_path = target_config_dir / "inference" / "routing_profiles.toml"
    pipelex_toml_path = target_config_dir / "pipelex.toml"

    check_config = focus in {InitFocus.ALL, InitFocus.CONFIG}
    check_credentials = focus in {InitFocus.ALL, InitFocus.CONFIG, InitFocus.INFERENCE}
    check_inference = focus in {InitFocus.ALL, InitFocus.INFERENCE}
    check_routing = focus == InitFocus.ROUTING
    check_telemetry = focus in {InitFocus.ALL, InitFocus.TELEMETRY}

    is_first_time_backends_setup = not backends_toml_path.exists()

    needs_config, needs_inference, needs_routing, needs_telemetry = determine_needs(
        reset=reset,
        check_config=check_config,
        check_inference=check_inference,
        check_routing=check_routing,
        check_telemetry=check_telemetry,
        backends_toml_path=backends_toml_path,
        routing_profiles_toml_path=routing_profiles_toml_path,
        telemetry_config_path=telemetry_config_path,
        target_config_dir=target_config_dir,
    )
    # `init_config` never copies `inference/`, so a configuration reset on a directory with no `backends.toml` is a
    # first setup, and sets up inference too, whatever the focus.
    if needs_config and is_first_time_backends_setup:
        needs_inference = True

    # Every directory a boot reads, not only the target, read together: a profile one of them activates can be defined in the
    # other, and a former release's files there stop the boot as surely.
    former_release_config_dirs = list(config_manager.existing_config_dirs)
    former_release_findings = [findings for findings in detect_former_release_across(config_dirs=former_release_config_dirs) if not findings.is_clean]
    boot_blockers = former_release_boot_blockers(
        backends_library_paths=config_manager.backends_file_paths(),
        routing_profile_library_paths=config_manager.routing_profiles_file_paths(),
    )

    return InitInspection(
        focus=focus,
        target_config_dir=target_config_dir,
        for_project=local,
        reset=reset,
        backends_toml_path=backends_toml_path,
        routing_profiles_toml_path=routing_profiles_toml_path,
        telemetry_config_path=telemetry_config_path,
        pipelex_toml_path=pipelex_toml_path,
        pipelex_toml_exists=pipelex_toml_path.is_file(),
        is_first_time_backends_setup=is_first_time_backends_setup,
        configured_execution=read_run_execution(pipelex_toml_path=pipelex_toml_path),
        check_credentials=check_credentials,
        check_inference=check_inference,
        check_routing=check_routing,
        needs_config=needs_config,
        needs_inference=needs_inference,
        needs_routing=needs_routing,
        needs_telemetry=needs_telemetry,
        former_release_config_dirs=former_release_config_dirs,
        former_release_findings=former_release_findings,
        former_release_boot_blockers=boot_blockers,
    )


def describe_former_release_findings(*, findings: list[FormerReleaseFindings], blockers: list[FormerReleaseFinding]) -> str:
    """What a former release left, in words: what of it stops the boot, the files it is in, and what the cleanup does.

    The findings that stop the boot are spelled out; the rest are counted by file, since `pipelex migrate --dry-run`
    lists every change for whoever wants each one.

    Args:
        findings: What the former release left, per directory.
        blockers: What of it stops this machine's boot, as `former_release_boot_blockers` reads the files the boot merges.
    """
    lead = (
        "This machine was set up by a former Pipelex release, which ran models through the Pipelex Gateway or Pipelex Manifold, "
        "and this release has neither."
    )
    if blockers:
        lines = [f"{lead} Pipelex cannot start until what that release left is cleaned up:", *(f"• {finding.description}" for finding in blockers)]
    else:
        lines = [f"{lead} What that release left no longer stops Pipelex from starting, and is still worth removing."]
    file_count = sum(len(directory_findings.file_paths) for directory_findings in findings)
    lines += ["", f"It is in {file_count} file(s):"]
    for directory_findings in findings:
        relative_paths = [path.relative_to(directory_findings.config_dir).as_posix() for path in directory_findings.file_paths]
        lines.append(f"• in '{directory_findings.config_dir}': {', '.join(relative_paths)}")
    lines += [
        "",
        (
            "The cleanup removes it and keeps a copy of each file it changes or removes; when the active routing profile is one of that "
            f"release's, it moves it to '{kit_default_routing_profile_name()}'. Run `{MIGRATE_COMMAND} --dry-run` to see each change."
        ),
    ]
    return "\n".join(lines)


def offer_former_release_cleanup(*, console: Console, inspection: InitInspection) -> None:
    """Say what a former release left, and clean it up on a yes.

    The cleanup is `pipelex migrate`'s first step, the same write pass with the same copies kept. A no leaves the files
    as they are and the setup goes on: what it writes into the target replaces that directory's inference files, but
    not the files beside them nor the other directory's, which go on stopping the boot until the cleanup runs. Only
    asked of a person: nothing removes or rewrites a user's files without a yes.
    """
    console.print()
    console.print(
        Panel(
            escape(describe_former_release_findings(findings=inspection.former_release_findings, blockers=inspection.former_release_boot_blockers)),
            title="[bold yellow]Left by a former release[/bold yellow]",
            border_style="yellow",
        )
    )
    if not Confirm.ask("[bold]Clean it up now?[/bold]", default=True):
        until = " Pipelex will not start until then." if inspection.former_release_boot_blockers else ""
        console.print(f"[yellow]Left as it is.[/yellow] [cyan]{MIGRATE_COMMAND}[/cyan] cleans it up whenever you are ready.{until}")
        return
    cleanup = apply_former_release_cleanup(config_dirs=inspection.former_release_config_dirs)
    if cleanup.still_blocking:
        console.print(
            f"[yellow]⚠ Pipelex still cannot start after the cleanup, as marked above. Fix what is named there, then run "
            f"[cyan]{MIGRATE_COMMAND}[/cyan] to check.[/yellow]"
        )
    elif cleanup.needs_attention:
        console.print(
            f"[yellow]⚠ Some files could not be cleaned up, as marked above. Run [cyan]{MIGRATE_COMMAND}[/cyan] once they can be written.[/yellow]"
        )
    else:
        console.print(f"[green]✓[/green] Cleaned up {len(cleanup.applied_files)} file(s); a copy of each original is beside it.")


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
    asks_setup_path: bool = False,
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
        asks_setup_path: Whether the run will ask where runs execute.

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
            asks_setup_path=asks_setup_path,
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


def choose_initialization(*, console: Console, inspection: InitInspection, skip_confirmation: bool) -> InitChoices:
    """Stage 2: offer the cleanup of what a former release left, confirm, then ask where runs execute when this run decides it.

    Args:
        console: Rich Console instance for user interaction.
        inspection: What stage 1 found.
        skip_confirmation: Ask nothing (`pipelex doctor --fix`): what a former release left is not offered and not
            cleaned up, since the doctor asks about it itself; the confirmation is skipped, and where runs execute is
            the one the target's `[run] execution` already sets, local for a `pipelex.toml` that sets none, and the
            hosted Pipelex API only for a brand-new home with no `pipelex.toml` yet.

    Returns:
        The choices stage 3 executes.

    Raises:
        typer.Exit: If the person cancels at the confirmation.
    """
    if inspection.former_release_findings and not skip_confirmation:
        offer_former_release_cleanup(console=console, inspection=inspection)

    if skip_confirmation:
        console.print()
        return InitChoices(setup_path=inspection.unattended_setup_path, interactive=False)

    confirm_initialization(
        console=console,
        needs_config=inspection.needs_config,
        needs_inference=inspection.needs_inference,
        needs_routing=inspection.needs_routing,
        needs_telemetry=inspection.needs_telemetry,
        # A reset that keeps hosted runs asks for no provider key, as the execute stage skips that step.
        check_credentials=inspection.check_credentials and not inspection.keeps_hosted_runs,
        reset=inspection.reset,
        focus=inspection.focus,
        asks_setup_path=inspection.asks_setup_path,
    )
    setup_path: SetupPath | None = None
    if inspection.asks_setup_path:
        console.print()
        setup_path = prompt_setup_path(console=console, default=DEFAULT_SETUP_PATH)
    return InitChoices(setup_path=setup_path, interactive=True)


def _reset_inference_files(*, console: Console, inspection: InitInspection) -> None:
    """Copy the kit's inference files over the target's (`init_config` skips `inference/`)."""
    template_inference_dir = Path(str(get_kit_configs_dir())) / "inference"
    target_inference_dir = inspection.target_config_dir / "inference"

    # Reset backends.toml
    template_backends_path = template_inference_dir / "backends.toml"
    inspection.backends_toml_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_backends_path, inspection.backends_toml_path)

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


def _suggest_extension(*, console: Console) -> None:
    """Offer the IDE extension, as the local path's backend step does."""
    try:
        suggest_extension_install_if_needed(console=console)
    except EOFError as exc:
        # No stdin available for the install prompt — skip the optional IDE extension suggestion.
        log.debug(f"IDE extension suggestion skipped: {exc}")


def execute_initialization(*, console: Console, inspection: InitInspection, choices: InitChoices) -> None:
    """Stage 3: write the files and run the steps the inspection and the choices call for.

    The local path runs the backends, routing and credentials steps; the hosted path leaves the kit's inference files
    as written, writes the hosted default, and, once every file is written, makes sure hosted runs have a key.

    Args:
        console: Rich Console instance for output.
        inspection: What stage 1 found.
        choices: What stage 2 settled.
    """
    target_config_dir = inspection.target_config_dir
    backends_toml_path = inspection.backends_toml_path
    setup_path = choices.setup_path
    kept_execution = inspection.kept_execution

    # Step 1: Initialize config if needed (init_config skips inference/, which the inference step handles)
    if inspection.needs_config:
        console.print()
        init_config(reset=inspection.reset, target_dir=target_config_dir)
        if kept_execution is not None:
            # The reset copied the kit's default over where runs execute, a choice this run did not ask about again.
            write_run_execution(pipelex_toml_path=inspection.pipelex_toml_path, execution=kept_execution)

    first_time_setup = inspection.is_first_time_backends_setup

    # Step 2: Set up inference if needed, and where runs execute when this run decides it
    if inspection.needs_inference:
        console.print()

        if inspection.reset:
            _reset_inference_files(console=console, inspection=inspection)
            first_time_setup = True  # Treat as first-time setup since we just replaced the files

        match setup_path:
            case SetupPath.HOSTED:
                # Hosted runs use none of this machine's backends: the kit's inference files stay as written.
                apply_setup_path_setting(
                    console=console,
                    setup_path=setup_path,
                    pipelex_toml_path=inspection.pipelex_toml_path,
                    project_config_dir=config_manager.project_config_dir,
                )
                if choices.interactive:
                    _suggest_extension(console=console)
            case SetupPath.LOCAL | None:
                customize_backends_config(is_first_time_setup=first_time_setup, target_config_dir=target_config_dir)

                # Automatically set up routing after backends (unless routing is the specific focus)
                if not inspection.check_routing:
                    selected_backend_keys = get_selected_backend_keys(backends_toml_path)
                    if selected_backend_keys:
                        customize_routing_profile(selected_backend_keys, target_config_dir=target_config_dir)

                if setup_path is not None:
                    console.print()
                    apply_setup_path_setting(
                        console=console,
                        setup_path=setup_path,
                        pipelex_toml_path=inspection.pipelex_toml_path,
                        project_config_dir=config_manager.project_config_dir,
                    )

    # Step 2.5: Prompt for missing credentials, which only runs on this machine use
    runs_hosted = (setup_path is not None and setup_path.is_hosted) or inspection.keeps_hosted_runs
    if inspection.check_credentials and not runs_hosted:
        prompt_credentials(console=console, backends_toml_path=backends_toml_path)

    # Step 3: Set up routing profile if specifically requested
    if inspection.needs_routing:
        console.print()

        # If reset is True, copy the template file first
        if inspection.reset:
            routing_profiles_toml_path = inspection.routing_profiles_toml_path
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
    if inspection.needs_telemetry:
        setup_telemetry(console=console, telemetry_config_path=inspection.telemetry_config_path, for_project=inspection.for_project)

    # Step 5: Hosted runs need a key. Last, so every file is written before a sign-in that can take minutes.
    if setup_path is not None and setup_path.is_hosted:
        try:
            ensure_pipelex_api_key(console=console, interactive=choices.interactive)
        except OSError as exc:
            # Every file is written by now, so the setup stands; only the key is missing, and the login is its remedy.
            console.print(f"[yellow]⚠ Your setup is saved, but no Pipelex API key was: {escape(str(exc))}[/yellow]")
            console.print(f"Run [cyan]pipelex login[/cyan] (or [cyan]{LOGIN_PASTE_COMMAND}[/cyan]) to get one.")

    console.print()


def init_cmd(
    focus: InitFocus = InitFocus.ALL,
    *,
    skip_confirmation: bool = False,
    local: bool = False,
):
    """Initialize Pipelex: configuration files, where runs execute, inference backends, credentials, routing, and telemetry.

    Note: Config updates are not yet supported. This command always performs a full reset
    of the configuration, overwriting any existing files.

    Args:
        focus: What to initialize - 'all', 'config', 'credentials', 'inference', 'routing', or 'telemetry'
        skip_confirmation: If True, ask nothing (used when called from doctor --fix): leave what a former release left
            to the doctor's own question, skip the confirmation, keep the `[run] execution` already set (local for a
            `pipelex.toml` that sets none), take the hosted Pipelex API only for a brand-new home with no
            `pipelex.toml`, and print `pipelex login` instead of opening a browser.
        local: If True, create project-level .pipelex/ at the detected project root.
            Otherwise, create the home configuration directory (~/.pipelex/, or PIPELEX_HOME).
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

    inspection = inspect_initialization(focus=focus, local=local)
    console.print(f"[dim]Target directory: {escape(str(inspection.target_config_dir))}[/dim]")

    # Show info message if config already exists
    if not inspection.is_first_time_backends_setup and not skip_confirmation:
        console.print()
        console.print("[dim]ℹ Config update requires running a full reset.[/dim]")

    try:
        choices = choose_initialization(console=console, inspection=inspection, skip_confirmation=skip_confirmation)
        execute_initialization(console=console, inspection=inspection, choices=choices)

    except typer.Exit:
        # Re-raise Exit exceptions
        raise
    except Exception as exc:  # ruff: ignore[blind-except]
        # Command-level boundary: any unexpected init failure is reported as a warning and the command returns without crashing.
        console.print(f"\n[red]⚠ Warning: Initialization failed: {escape(str(exc))}[/red]", style="bold")
        if inspection.needs_config:
            console.print("[red]Please run 'pipelex init config' manually.[/red]")
        return
