"""Doctor command for checking Pipelex configuration health."""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from pipelex import log
from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cli.commands.update_cmd import update_cmd
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.cogt.exceptions import (
    GatewayUnknownModelError,
    InferenceBackendCredentialsError,
    InferenceBackendLibraryError,
    InferenceBackendLibraryNotFoundError,
    InferenceBackendLibraryValidationError,
    ModelDeckNotFoundError,
    ModelDeckValidationError,
    RoutingProfileDisabledBackendError,
    RoutingProfileLibraryNotFoundError,
)
from pipelex.cogt.model_backends.backend_credentials import BackendCredentialsErrorMsgFactory
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport, InferenceBackendLibrary
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.models.deck_manifest import DeckFileStatus, DeckSyncReport, compute_deck_sync_report, status_rich_label
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.config import get_config
from pipelex.core.validation import report_validation_error
from pipelex.hub import PipelexHub, get_console, set_pipelex_hub
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.environment import get_optional_env
from pipelex.system.pipelex_service.exceptions import (
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.pipelex_service_config import (
    is_pipelex_gateway_enabled,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.remote_config_fetcher import RemoteConfigFetcher
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryConfig
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.dict_utils import extract_vars_from_strings_recursive
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.placeholder import value_is_placeholder
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_path
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.system.pipelex_service.types import RemoteConfigSource


class ConfigLocationInfo(BaseModel):
    """Information about the resolved configuration location."""

    config_dir: str
    is_project_local: bool
    project_root: str | None = None
    global_config_dir: str


def gather_config_location() -> ConfigLocationInfo:
    """Gather information about the current configuration location.

    Returns:
        ConfigLocationInfo with resolved paths and location type.
    """
    effective_config_dir = config_manager.pipelex_config_dir
    project_root = config_manager.project_root
    project_config_dir = config_manager.project_config_dir
    global_config_dir = config_manager.global_config_dir

    return ConfigLocationInfo(
        config_dir=str(effective_config_dir),
        is_project_local=project_config_dir is not None,
        project_root=str(project_root) if project_root is not None else None,
        global_config_dir=str(global_config_dir),
    )


class BackendFileReport(BaseModel):
    """Report on the health of an individual backend configuration file."""

    backend_name: str
    file_path: str
    is_valid: bool
    error_message: str | None = None
    has_kit_template: bool = False


def check_config_files(config_dir: Path | None = None) -> tuple[bool, int, str]:
    """Check if configuration files are present and main config is valid.

    Args:
        config_dir: Explicit config directory override (e.g. for --global).
            If None, uses layered resolution (project .pipelex/ → global ~/.pipelex/).

    Returns:
        Tuple of (is_healthy, missing_count, message)
    """
    effective_config_dir = config_dir or config_manager.pipelex_config_dir

    # Check for missing files
    try:
        missing_count = init_config(reset=False, dry_run=True, target_dir=str(effective_config_dir))
    except (PipelexCLIError, OSError) as exc:
        return False, 0, f"Error checking config files: {exc}"

    # Check if main config can be loaded using the hub's setup.
    # Note: load_config() uses config_manager's own resolution chain (package → global → project)
    # which may differ from config_dir when --global is used. This is acceptable for a diagnostic
    # check — the existence check guards the path, while load_config() validates the merged config.
    pipelex_config_path = config_manager.resolve_config_file("pipelex.toml", config_dir=config_dir)
    if path_exists(pipelex_config_path):
        try:
            # Suppress stderr and stdout to prevent tracebacks from being printed
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                config = config_manager.load_config()
                PipelexConfig.model_validate(config)
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
            msg = f"Configuration validation failed:\n{validation_error_msg}"
            return False, 0, msg
        except (TomlError, OSError) as exc:
            return False, 0, f"Error loading pipelex.toml: {exc}"

    # Report results
    if missing_count == 0:
        return True, 0, "All configuration files present and valid"
    return False, missing_count, f"{missing_count} configuration file(s) missing"


def check_telemetry_config(config_dir: Path | None = None) -> tuple[bool, str]:
    """Check if telemetry configuration is valid.

    Args:
        config_dir: Explicit config directory override (e.g. for --global).
            If None, uses layered resolution (project .pipelex/ → global ~/.pipelex/).

    Returns:
        Tuple of (is_healthy, message)
    """
    telemetry_config_path = config_manager.resolve_config_file(TELEMETRY_CONFIG_FILE_NAME, config_dir=config_dir)

    try:
        toml_doc = load_toml_from_path(telemetry_config_path)
    except FileNotFoundError:
        return False, "Telemetry configuration file not found"
    except TomlError as exc:
        return False, f"TOML syntax error: {exc}"

    try:
        telemetry_config = TelemetryConfig.model_validate(toml_doc)
        return True, f"Telemetry configured (mode: {telemetry_config.custom_posthog.mode})"
    except ValidationError:
        # Check if this looks like the old config format (has telemetry_mode at root level)
        if "custom_posthog" not in toml_doc and ("telemetry_mode" in toml_doc or "project_api_key" in toml_doc):
            return False, "Config format has changed - run 'pipelex init telemetry' to update"
        return False, "Invalid configuration - run 'pipelex init telemetry' to fix"


def check_backend_credentials(config_dir: Path | None = None) -> tuple[bool, dict[str, BackendCredentialsReport], str]:
    """Check if backend credentials are properly configured.

    Args:
        config_dir: Explicit config directory override (e.g. for --global).
            If None, uses layered resolution (project .pipelex/ → global ~/.pipelex/).

    Returns:
        Tuple of (is_healthy, backend_reports_dict, summary_message)
    """
    backends_toml_path = config_manager.resolve_config_file(os.path.join("inference", "backends.toml"), config_dir=config_dir)

    if not path_exists(backends_toml_path):
        return False, {}, "Backend configuration file not found"

    try:
        backends_dict = load_toml_from_path(backends_toml_path)
        backend_reports: dict[str, BackendCredentialsReport] = {}
        all_backends_valid = True

        for backend_name, backend_dict in backends_dict.items():
            # Skip internal backend
            if backend_name == "internal":
                continue

            # Only check enabled backends
            if isinstance(backend_dict, dict):
                enabled = backend_dict.get("enabled", True)  # type: ignore[union-attr]
            else:
                enabled = True
            if not enabled:
                continue

            # Extract all variable placeholders from the backend config
            required_vars_set = extract_vars_from_strings_recursive(backend_dict)
            required_vars = sorted(required_vars_set)

            # Check status of each variable
            missing_vars: list[str] = []
            placeholder_vars: list[str] = []

            for var_name in required_vars:
                var_value = get_optional_env(var_name)
                if var_value is None:
                    missing_vars.append(var_name)
                elif value_is_placeholder(var_value):
                    placeholder_vars.append(var_name)

            # Determine if all credentials are valid for this backend
            backend_valid = len(missing_vars) == 0 and len(placeholder_vars) == 0

            # Create report for this backend
            backend_report = BackendCredentialsReport(
                backend_name=backend_name,
                required_vars=required_vars,
                missing_vars=missing_vars,
                placeholder_vars=placeholder_vars,
                all_credentials_valid=backend_valid,
            )
            backend_reports[backend_name] = backend_report

            if not backend_valid:
                all_backends_valid = False

        if all_backends_valid:
            backend_count = len(backend_reports)
            return True, backend_reports, f"All {backend_count} enabled backend(s) have valid credentials"

        # Count backends with issues
        backends_with_issues = sum(1 for r in backend_reports.values() if not r.all_credentials_valid)
        return False, backend_reports, f"{backends_with_issues} backend(s) have missing or invalid credentials"

    except Exception as exc:  # noqa: BLE001
        # Doctor probe: the credential scan spans TOML load, env lookups and placeholder checks; any failure is reported as a finding.
        return False, {}, f"Error checking backend credentials: {exc}"


def check_kit_template_exists(backend_name: str) -> bool:
    """Check if a kit template exists for the given backend.

    Args:
        backend_name: Name of the backend to check

    Returns:
        True if a template exists in the kit, False otherwise
    """
    try:
        kit_configs_dir = get_kit_configs_dir()
        # The kit configs are in a Traversable (from importlib.resources)
        # We need to check if the backend file exists
        backends_dir = kit_configs_dir / "inference" / "backends"
        backend_file = backends_dir / f"{backend_name}.toml"

        # For Traversable, we check if it's a file
        return backend_file.is_file()
    except Exception:  # noqa: BLE001
        # Doctor probe: kit-template existence is a best-effort bool check; any lookup failure means "no template".
        return False


def replace_backend_file(backend_name: str, dry_run: bool = False, config_dir: Path | None = None) -> bool:
    """Replace a backend configuration file with the kit template.

    Args:
        backend_name: Name of the backend to replace
        dry_run: If True, only report what would be done without actually doing it
        config_dir: Explicit config directory path. If None, uses config_manager.pipelex_config_dir.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get kit template path
        kit_configs_dir = get_kit_configs_dir()
        template_file = kit_configs_dir / "inference" / "backends" / f"{backend_name}.toml"

        if not template_file.is_file():
            return False

        # Read template content
        template_content = template_file.read_text(encoding="utf-8")

        # Determine target path
        resolved_config_dir = config_dir or config_manager.pipelex_config_dir
        target_dir = Path(resolved_config_dir) / "inference" / "backends"
        target_file = target_dir / f"{backend_name}.toml"

        if dry_run:
            return True

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write the file
        target_file.write_text(template_content, encoding="utf-8")
        return True

    except Exception:  # noqa: BLE001
        # Doctor --fix helper: the kit-template copy is best-effort; any failure means "could not replace" (returns False).
        return False


def check_backend_files(config_dir: Path | None = None) -> tuple[bool, dict[str, BackendFileReport], str]:
    """Check individual backend configuration files for validity.

    Args:
        config_dir: Explicit config directory override (e.g. for --global).
            If None, uses layered resolution (project .pipelex/ → global ~/.pipelex/).

    Returns:
        Tuple of (is_healthy, backend_file_reports_dict, summary_message)
    """
    backends_dir_path = config_manager.resolve_config_file(os.path.join("inference", "backends"), config_dir=config_dir)

    if not path_exists(backends_dir_path):
        return True, {}, "No backend files to check"

    # Get list of enabled backends from backends.toml
    backends_toml_path = config_manager.resolve_config_file(os.path.join("inference", "backends.toml"), config_dir=config_dir)
    if not path_exists(backends_toml_path):
        return True, {}, "No backends.toml to check"

    try:
        backends_dict = load_toml_from_path(backends_toml_path)
    except (TomlError, OSError) as exc:
        return False, {}, f"Error loading backends.toml: {exc}"

    backend_file_reports: dict[str, BackendFileReport] = {}
    all_valid = True

    # Check each enabled backend
    for backend_name, backend_dict in backends_dict.items():
        # Skip internal backend
        if backend_name == "internal":
            continue

        # Only check enabled backends
        if isinstance(backend_dict, dict):
            the_backend_dict: dict[str, Any] = backend_dict  # type: ignore[reportUnknownMemberType]
            enabled = the_backend_dict.get("enabled", True)
        else:
            enabled = True

        if not enabled:
            continue

        # Check if backend file exists
        backend_file_path = str(backends_dir_path / f"{backend_name}.toml")

        if not path_exists(backend_file_path):
            # No separate file - this is OK, configuration might be inline
            continue

        # Try to validate the backend file by loading it
        is_valid = True
        error_message = None

        try:
            # Create a temporary backend library and try to load this backend
            secrets_provider = EnvSecretsProvider()
            temp_library = InferenceBackendLibrary.make_empty()

            # Try to load just this backend's specs
            temp_library.load(
                secrets_provider=secrets_provider,
                backends_library_path=str(backends_toml_path),
                backends_dir_path=str(backends_dir_path),
                include_disabled=False,
            )

        except InferenceBackendLibraryError as exc:
            # Check if this specific backend caused the error
            error_str = str(exc)
            if backend_name in error_str or backend_file_path in error_str:
                is_valid = False
                error_message = error_str
                all_valid = False
        except Exception as exc:  # noqa: BLE001
            # Doctor probe: a backend load can fail in many ways; any error naming this backend is recorded as its validation failure.
            error_str = str(exc)
            if backend_name in error_str or backend_file_path in error_str:
                is_valid = False
                error_message = error_str
                all_valid = False

        # Check if kit template exists for this backend
        has_kit_template = check_kit_template_exists(backend_name)

        # Create report
        backend_file_report = BackendFileReport(
            backend_name=backend_name,
            file_path=backend_file_path,
            is_valid=is_valid,
            error_message=error_message,
            has_kit_template=has_kit_template,
        )
        backend_file_reports[backend_name] = backend_file_report

    if all_valid:
        return True, backend_file_reports, "All backend files are valid"

    # Count backends with issues
    invalid_count = sum(1 for r in backend_file_reports.values() if not r.is_valid)
    return False, backend_file_reports, f"{invalid_count} backend file(s) have validation errors"


def display_health_report(
    config_healthy: bool,
    config_message: str,
    config_missing_count: int,
    telemetry_healthy: bool,
    telemetry_message: str,
    backends_healthy: bool,
    backends_message: str,
    backend_credential_reports: dict[str, BackendCredentialsReport],
    models_healthy: bool,
    models_message: str,
    backend_file_reports: dict[str, BackendFileReport],
    deck_healthy: bool,
    deck_message: str,
    deck_report: DeckSyncReport,
    config_location: ConfigLocationInfo,
    fix_mode: bool = False,
) -> None:
    """Display a comprehensive health report.

    Args:
        config_healthy: Whether config files check passed
        config_message: Message about config files status
        config_missing_count: Number of missing config files
        telemetry_healthy: Whether telemetry check passed
        telemetry_message: Message about telemetry status
        backends_healthy: Whether backends check passed
        backends_message: Message about backends status
        backend_credential_reports: Dict of backend credential reports
        models_healthy: Whether models check passed
        models_message: Message about models status
        backend_file_reports: Dict of backend file validation reports
        deck_healthy: Whether the model deck is in sync with the kit shipped by this pipelex version
        deck_message: Summary message about deck sync status
        deck_report: Per-file sync status report (used to render the per-file detail when not healthy)
        config_location: Resolved configuration location information
        fix_mode: Whether we're in interactive fix mode (--fix flag)
    """
    all_healthy = config_healthy and telemetry_healthy and backends_healthy and models_healthy and deck_healthy

    # Overall status panel
    if all_healthy:
        status_text = Text("Overall Status: ✅ All systems healthy", style="bold green")
    else:
        status_text = Text("Overall Status: ⚠️  Issues Found", style="bold yellow")

    status_panel = Panel(
        status_text,
        title="[bold cyan]Pipelex Health Check[/bold cyan]",
        border_style="cyan" if all_healthy else "yellow",
        padding=(1, 2),
    )
    console = get_console()
    console.print()
    console.print(status_panel)
    console.print()

    # Configuration Location section
    console.print("[bold]Configuration Location[/bold]")
    if config_location.is_project_local:
        console.print(f"  [green]✓[/green] Using project config: [cyan]{config_location.config_dir}[/cyan]")
        console.print(f"  [dim]Project root: {config_location.project_root}[/dim]")
        console.print(f"  [dim]Global config: {config_location.global_config_dir}[/dim]")
    else:
        console.print(f"  [green]✓[/green] Using global config: [cyan]{config_location.config_dir}[/cyan]")
        console.print("  [dim]No project .pipelex/ directory found[/dim]")
    console.print()

    # Configuration Files section
    console.print("[bold]Configuration Files[/bold]")
    if config_healthy:
        console.print(f"  [green]✓[/green] {config_message}")
    else:
        console.print(f"  [red]✗[/red] {config_message}")
    console.print()

    # Telemetry Configuration section
    console.print("[bold]Telemetry Configuration[/bold]")
    if telemetry_healthy:
        console.print(f"  [green]✓[/green] {telemetry_message}")
    else:
        console.print(f"  [red]✗[/red] {telemetry_message}")
    console.print()

    # Backend Credentials section
    console.print("[bold]Backend Credentials[/bold]")
    if backends_healthy:
        console.print(f"  [green]✓[/green] {backends_message}")
    elif not backend_credential_reports:
        # No backends were checked (e.g., file not found)
        console.print(f"  [red]✗[/red] {backends_message}")
    else:
        console.print(f"  [yellow]⚠[/yellow]  {backends_message}")
        console.print()

        # Show details for each backend
        bad_backend_credential_reports: dict[str, BackendCredentialsReport] = {}
        for backend_name, backend_credential_report in backend_credential_reports.items():
            if backend_credential_report.all_credentials_valid:
                console.print(f"  [dim]{backend_name}[/dim]")
                console.print("    [green]✓[/green] All credentials set")
            else:
                bad_backend_credential_reports[backend_name] = backend_credential_report
                console.print(f"  [bold]{backend_name}[/bold]")
                if backend_credential_report.missing_vars:
                    console.print(f"    [red]✗[/red] Missing: {', '.join(backend_credential_report.missing_vars)}")
                if backend_credential_report.placeholder_vars:
                    console.print(f"    [yellow]⚠[/yellow] Placeholders: {', '.join(backend_credential_report.placeholder_vars)}")

        error_msg = BackendCredentialsErrorMsgFactory.make_comprehensive_error_msg(backend_credential_reports=bad_backend_credential_reports)
        console.print(error_msg)
    console.print()

    # Models section
    console.print("[bold]Models[/bold]")
    if models_healthy:
        console.print(f"  [green]✓[/green] {models_message}")
    else:
        console.print(f"  [red]✗[/red] {models_message}")

        # Show details for backend file issues if any
        if backend_file_reports:
            invalid_backends = {name: report for name, report in backend_file_reports.items() if not report.is_valid}
            if invalid_backends:
                console.print()
                for backend_name, backend_file_report in invalid_backends.items():
                    console.print(f"  [bold]{backend_name}[/bold]")
                    if backend_file_report.has_kit_template:
                        console.print("    [yellow]⚠[/yellow] Backend configuration format may be outdated")
                        console.print("    [dim]Template available for replacement[/dim]")
                    else:
                        console.print("    [yellow]⚠[/yellow] Backend configuration has errors")
                        console.print("    [dim]This appears to be a custom backend - manual fix required[/dim]")
                    if backend_file_report.error_message:
                        # Show first line of error
                        error_lines = backend_file_report.error_message.split("\n")
                        console.print(f"    [dim]{error_lines[0][:100]}[/dim]")
    console.print()

    # Model Deck section
    console.print("[bold]Model Deck[/bold]")
    if deck_healthy:
        console.print(f"  [green]✓[/green] {deck_message}")
    else:
        console.print(f"  [yellow]⚠[/yellow]  {deck_message}")
        # Per-file detail when there are pending actions
        actionable_statuses = {name: status for name, status in deck_report.files.items() if status != DeckFileStatus.UP_TO_DATE}
        if actionable_statuses:
            for filename in sorted(actionable_statuses):
                status = actionable_statuses[filename]
                console.print(f"    [dim]{filename}[/dim] — {status_rich_label(status)}")
    console.print()

    # Recommended actions
    if not all_healthy:
        # Check what can be auto-fixed
        can_auto_fix_config = not config_healthy and config_missing_count > 0
        can_auto_fix_telemetry = not telemetry_healthy and (
            "not found" in telemetry_message.lower()
            or "format has changed" in telemetry_message.lower()
            or "invalid configuration" in telemetry_message.lower()
        )
        has_telemetry_validation_error = not telemetry_healthy and not can_auto_fix_telemetry

        # Check for backend file issues
        has_backend_file_issues = False
        can_auto_fix_backends = False
        has_custom_backend_issues = False
        if backend_file_reports:
            invalid_backends = {name: report for name, report in backend_file_reports.items() if not report.is_valid}
            if invalid_backends:
                has_backend_file_issues = True
                # Check if any have kit templates (auto-fixable)
                can_auto_fix_backends = any(report.has_kit_template for report in invalid_backends.values())
                # Check if any are custom backends (manual fix)
                has_custom_backend_issues = any(not report.has_kit_template for report in invalid_backends.values())

        # Determine if we have any recommendations to show
        has_deck_drift = not deck_healthy
        has_recommendations = (
            can_auto_fix_config
            or can_auto_fix_telemetry
            or has_telemetry_validation_error
            or (not backends_healthy and backend_credential_reports)
            or has_backend_file_issues
            or has_deck_drift
        )

        if has_recommendations:
            console.print("[bold]Possible Solutions[/bold]")

            if can_auto_fix_config:
                console.print("  • Run [cyan]pipelex init config[/cyan] to install missing configuration files")

            if can_auto_fix_telemetry:
                console.print("  • Run [cyan]pipelex init telemetry[/cyan] to configure telemetry preferences")

            if has_telemetry_validation_error and "pipelex init telemetry" not in telemetry_message:
                console.print(f"  • Fix validation errors in [cyan]{config_location.config_dir}/telemetry.toml[/cyan]")
                console.print("    or run [cyan]pipelex init telemetry[/cyan] to regenerate")

            if has_deck_drift:
                console.print("  • Run [cyan]pipelex update[/cyan] to refresh the model deck from the current kit")

            # Backend file issues
            if can_auto_fix_backends:
                if fix_mode:
                    # We're in fix mode, show what's happening next and the alternative
                    console.print("  • Interactive fixes for outdated backend configurations will be offered below")
                    console.print("  • Alternatively, run [cyan]pipelex init config[/cyan] to reset all configuration files")
                else:
                    # Not in fix mode, suggest running --fix
                    console.print("  • Run [cyan]pipelex doctor --fix[/cyan] to replace outdated backend configurations")
                    console.print("    [dim]or run[/dim] [cyan]pipelex init config[/cyan] [dim]to reset all configuration files[/dim]")

            if has_custom_backend_issues:
                invalid_custom = [name for name, report in backend_file_reports.items() if not report.is_valid and not report.has_kit_template]
                for backend_name in invalid_custom:
                    console.print(
                        f"  • Manually fix backend configuration in [cyan]{config_location.config_dir}/inference/backends/{backend_name}.toml[/cyan]"
                    )

            if not backends_healthy and backend_credential_reports:
                # Collect all missing and placeholder vars
                all_missing_vars: set[str] = set()
                all_placeholder_vars: set[str] = set()

                for backend_credential_report in backend_credential_reports.values():
                    if not backend_credential_report.all_credentials_valid:
                        all_missing_vars.update(backend_credential_report.missing_vars)
                        all_placeholder_vars.update(backend_credential_report.placeholder_vars)

                if all_missing_vars:
                    console.print("  • Set the following environment variables:")
                    for var_name in sorted(all_missing_vars):
                        console.print(f"    - {var_name}")

                if all_placeholder_vars:
                    console.print("  • Replace placeholder values for:")
                    for var_name in sorted(all_placeholder_vars):
                        console.print(f"    - {var_name}")

            console.print()

            # Only suggest --fix if there are auto-fixable issues AND we're not already in fix mode
            if not fix_mode and (can_auto_fix_config or can_auto_fix_telemetry or can_auto_fix_backends):
                console.print("[dim]Run[/dim] [cyan]pipelex doctor --fix[/cyan] [dim]to interactively fix auto-fixable issues.[/dim]")
                console.print()

        # Show Discord support for manual-fix issues (regardless of --fix flag)
        has_config_validation_error = not config_healthy and config_missing_count == 0
        has_backend_credential_issues = not backends_healthy and backend_credential_reports
        if has_config_validation_error or has_backend_credential_issues or has_telemetry_validation_error:
            console.print("[dim]If you need help with manual fixes:[/dim]")
            console.print("  [cyan]https://docs.pipelex.com[/cyan] - Documentation")
            console.print("  [cyan]https://go.pipelex.com/discord[/cyan] - Discord Community")
            console.print()


def check_deck_sync(config_dir: Path | None = None) -> tuple[bool, DeckSyncReport, str]:
    """Check whether the installed model deck is in sync with the kit shipped by this pipelex version.

    Args:
        config_dir: Explicit config directory override. If None, uses layered resolution.

    Returns:
        Tuple of (is_healthy, sync_report, summary_message)
    """
    # When no explicit config_dir is given, mirror runtime layered resolution so we report
    # against the deck that's actually in use (project .pipelex/ wins when it ships a deck,
    # otherwise we fall through to the global deck).
    deck_dir = Path(config_dir) / "inference" / "deck" if config_dir is not None else config_manager.model_decks_dir_path

    if not deck_dir.exists():
        # Match the existing doctor pattern: surface as healthy when the area isn't initialized,
        # since the missing-init advisory is handled by the config_files / backends checks above.
        return True, DeckSyncReport(kit_version="", installed_kit_version=None, manifest_present=False, files={}), "Deck directory not present"

    report = compute_deck_sync_report(deck_dir)
    if report.is_clean():
        return True, report, f"Deck is up to date with pipelex {report.kit_version}"

    actionable = [name for name, status in report.files.items() if status.needs_action]
    if not report.manifest_present:
        return False, report, "Deck manifest missing — run `pipelex update` to materialize a baseline"
    if report.installed_kit_version != report.kit_version:
        return (
            False,
            report,
            f"Deck installed for pipelex {report.installed_kit_version}, current is {report.kit_version} ({len(actionable)} file(s) need action)",
        )
    return False, report, f"{len(actionable)} deck file(s) need action"


def setup_doctor_runtime(
    log_config_overrides: Mapping[str, Any] | None = None,
    config_dir: Path | None = None,
) -> None:
    """Spin up a fresh PipelexHub and configure logging for doctor checks.

    Doctor intentionally bypasses ``Pipelex.make`` so it can diagnose a broken config
    without crashing during full init. This helper performs the minimum runtime setup
    that ``check_models`` requires — a hub with a loaded config, a hub-level console
    print target, and a configured logger — mirroring ``Pipelex.__init__`` step for
    step on that subset.

    The agent doctor passes ``AGENT_CLI_STDERR_LOG_FIELDS`` so the JSON envelope on
    stdout stays clean for downstream consumers. The human doctor passes nothing and
    inherits the user's configured log targets.

    Overrides are merged via ``LogConfig.model_validate`` (full re-validation) so that
    a wrong-typed override surfaces loudly instead of silently breaking downstream
    match/case dispatch on ``ConsoleTarget`` etc.

    ``log.configure`` is invoked through ``configure_if_unset`` so that if a library
    embedding or interleaved test has already configured logging, this call no-ops
    instead of raising the once-per-process ``RuntimeError``.

    Args:
        log_config_overrides: Optional mapping of ``LogConfig`` field names → values to
            merge into the loaded log_config before ``log.configure`` is called.
        config_dir: Optional explicit config dir (e.g. for ``--global``). When provided,
            project/global layering is bypassed and only this directory is read.

    Raises:
        PipelexConfigError: If config validation fails. Translation of
            ``pydantic.ValidationError`` to keep doctor's error surface stable.
    """
    pipelex_hub = PipelexHub()
    set_pipelex_hub(pipelex_hub)
    try:
        pipelex_hub.setup_config(config_cls=PipelexConfig, config_dir=config_dir)
    except ValidationError as validation_error:
        validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
        msg = f"Could not setup config because of: {validation_error_msg}"
        raise PipelexConfigError(msg) from validation_error

    log_config = get_config().pipelex.log_config
    if log_config_overrides is not None:
        log_config = LogConfig.model_validate({**log_config.model_dump(), **log_config_overrides})
    pipelex_hub.set_console_print_target(target=log_config.console_print_target)
    log.configure_if_unset(log_config=log_config)


def check_models(config_dir: Path | None = None) -> tuple[bool, str, dict[str, BackendFileReport]]:
    """Check if models are valid, including backend file validation.

    Assumes ``setup_doctor_runtime`` has already run — the function reads from the
    active hub and relies on ``log`` being configured.

    Args:
        config_dir: Explicit config directory override (e.g. for --global).
            If None, uses layered resolution (project .pipelex/ → global ~/.pipelex/).

    Returns:
        Tuple of (is_healthy, message, backend_file_reports)
    """
    # First check backend files individually
    backend_files_healthy, backend_file_reports, _ = check_backend_files(config_dir=config_dir)

    # If backend files have issues, report that immediately
    if not backend_files_healthy:
        invalid_backends = [name for name, report in backend_file_reports.items() if not report.is_valid]
        if invalid_backends:
            # Get the first error message for summary
            first_error = next((report.error_message for report in backend_file_reports.values() if report.error_message), "Unknown error")
            msg = f"Backend configuration error: {first_error}"
            return False, msg, backend_file_reports

    # Fetch gateway model specs if Gateway is enabled
    gateway_config: GatewayConfig | None = None
    gateway_config_source: RemoteConfigSource | None = None
    if is_pipelex_gateway_enabled():
        pipelex_service_config = load_pipelex_service_config_if_exists(config_dir=config_manager.global_config_dir)
        if pipelex_service_config is None:
            return False, "Pipelex Gateway is enabled but service configuration is missing", backend_file_reports
        if not pipelex_service_config.agreement.terms_accepted:
            return False, "Pipelex Gateway is enabled but terms have not been accepted", backend_file_reports
        try:
            result = RemoteConfigFetcher.fetch_remote_config()
            remote_config = result.config
            gateway_config_source = result.source
            gateway_config = GatewayConfig(
                model_specs=remote_config.backend_model_specs,
                aws_region=remote_config.aws_region,
            )
        except (RemoteConfigUnavailableError, RemoteConfigValidationError) as exc:
            return False, f"Failed to fetch Pipelex Gateway remote configuration: {exc}", backend_file_reports

    models_manager = ModelManager()
    secrets_provider = EnvSecretsProvider()
    try:
        models_manager.setup(
            secrets_provider=secrets_provider,
            gateway_config=gateway_config,
            gateway_config_source=gateway_config_source,
        )
        models_manager.validate_model_deck()
    except InferenceBackendLibraryError as exc:
        # Backend library error - try to identify which backend
        error_str = str(exc)
        # Parse error to see if we can identify a specific backend
        for backend_name in backend_file_reports:
            if backend_name in error_str:
                # Update the report for this backend
                if backend_name in backend_file_reports:
                    backend_file_reports[backend_name].is_valid = False
                    backend_file_reports[backend_name].error_message = error_str
        return False, f"Error checking models: {exc}", backend_file_reports
    except (
        RoutingProfileLibraryNotFoundError,
        InferenceBackendLibraryNotFoundError,
        ModelDeckNotFoundError,
        RoutingProfileDisabledBackendError,
        InferenceBackendLibraryValidationError,
        ModelDeckValidationError,
        InferenceBackendCredentialsError,
        GatewayUnknownModelError,
    ) as exc:
        return False, f"Error checking models: {exc}", backend_file_reports

    return True, "Models are valid", backend_file_reports


def doctor_cmd(
    fix: bool = False,
) -> None:
    """Check Pipelex configuration health and suggest fixes.

    Args:
        fix: If True, offer to fix detected issues interactively
    """
    console = get_console()
    try:
        do_doctor_cmd(fix=fix)

    except Exception as exc:  # noqa: BLE001
        # Handle unexpected errors gracefully without printing traces
        console.print()
        console.print(f"[red]✗ Unexpected error: {exc!s}[/red]")
        console.print()
        console.print("[dim]If you need help:[/dim]")
        console.print("  [cyan]https://docs.pipelex.com[/cyan] - Documentation")
        console.print("  [cyan]https://go.pipelex.com/discord[/cyan] - Discord Community")
        console.print()
        sys.exit(1)


def do_doctor_cmd(
    fix: bool = False,
) -> None:
    """Check Pipelex configuration health and suggest fixes.

    Args:
        fix: If True, offer to fix detected issues interactively
    """
    # Gather config location info
    config_location = gather_config_location()

    # Filesystem-only checks run BEFORE bootstrap: setup_doctor_runtime calls
    # load_config which materializes ~/.pipelex/ from kit templates as a side effect.
    # Running it first would turn check_config_files into a silent installer on a
    # fresh machine — it would always report healthy after the install.
    config_healthy, config_missing_count, config_message = check_config_files()
    telemetry_healthy, telemetry_message = check_telemetry_config()
    backends_healthy, backend_credential_reports, backends_message = check_backend_credentials()

    # Bootstrap the minimum runtime check_models depends on (hub + log.configure).
    # No overrides for the human CLI: it inherits the user's configured log targets.
    setup_doctor_runtime()

    models_healthy, models_message, backend_file_reports = check_models()
    deck_healthy, deck_report, deck_message = check_deck_sync()

    # Display report
    display_health_report(
        config_healthy=config_healthy,
        config_message=config_message,
        config_missing_count=config_missing_count,
        telemetry_healthy=telemetry_healthy,
        telemetry_message=telemetry_message,
        backends_healthy=backends_healthy,
        backends_message=backends_message,
        backend_credential_reports=backend_credential_reports,
        models_healthy=models_healthy,
        models_message=models_message,
        backend_file_reports=backend_file_reports,
        deck_healthy=deck_healthy,
        deck_message=deck_message,
        deck_report=deck_report,
        config_location=config_location,
        fix_mode=fix,
    )

    all_healthy = config_healthy and telemetry_healthy and backends_healthy and models_healthy and deck_healthy

    # Exit code: 0 if healthy, 1 if issues found
    if all_healthy:
        sys.exit(0)

    # Determine what can be auto-fixed
    can_fix_config = not config_healthy and config_missing_count > 0
    # Telemetry can be fixed if not found, format changed, OR invalid configuration
    can_fix_telemetry = not telemetry_healthy and (
        "not found" in telemetry_message.lower()
        or "format has changed" in telemetry_message.lower()
        or "invalid configuration" in telemetry_message.lower()
    )

    # Check for backend file issues that can be auto-fixed
    can_fix_backends = False
    fixable_backends: list[tuple[str, BackendFileReport]] = []
    if backend_file_reports:
        invalid_backends = [(name, report) for name, report in backend_file_reports.items() if not report.is_valid]
        fixable_backends = [(name, report) for name, report in invalid_backends if report.has_kit_template]
        can_fix_backends = len(fixable_backends) > 0

    can_fix_deck = not deck_healthy and deck_report.kit_version != ""

    has_auto_fixable_issues = can_fix_config or can_fix_telemetry or can_fix_backends or can_fix_deck

    # Determine what requires manual fixes (excludes auto-fixable issues)
    has_config_validation_error = not config_healthy and config_missing_count == 0
    # Telemetry validation error only if it's not auto-fixable (not "not found" and not "format has changed")
    has_telemetry_validation_error = not telemetry_healthy and not can_fix_telemetry
    has_backend_credential_issues = not backends_healthy and backend_credential_reports

    # If --fix flag is provided, offer to fix auto-fixable issues
    if fix and has_auto_fixable_issues:
        console = get_console()
        console.print("[bold yellow]Interactive Fix Mode[/bold yellow]")
        console.print()

        # Fix missing config files
        if can_fix_config:
            if Confirm.ask(f"[bold]Install {config_missing_count} missing configuration file(s)?[/bold]", default=True):
                try:
                    console.print()
                    init_cmd(focus=InitFocus.CONFIG, skip_confirmation=True)
                    console.print("[green]✓[/green] Configuration files installed")
                except Exception as exc:  # noqa: BLE001
                    # Doctor --fix handler: wraps the whole init_cmd sub-command; a fix failure is reported and the doctor run continues.
                    console.print(f"[red]Failed to install configuration files: {exc!s}[/red]")
                console.print()

        # Fix missing or outdated telemetry config
        if can_fix_telemetry:
            is_format_change = "format has changed" in telemetry_message.lower()
            is_invalid_config = "invalid configuration" in telemetry_message.lower()
            if is_format_change:
                prompt_msg = "[bold]Reset telemetry configuration using the new format?[/bold]"
            elif is_invalid_config:
                prompt_msg = "[bold]Reset telemetry configuration to fix validation errors?[/bold]"
            else:
                prompt_msg = "[bold]Configure telemetry preferences?[/bold]"
            if Confirm.ask(prompt_msg, default=True):
                try:
                    console.print()
                    init_cmd(focus=InitFocus.TELEMETRY, skip_confirmation=True)
                    console.print("[green]✓[/green] Telemetry configured")
                except Exception as exc:  # noqa: BLE001
                    # Doctor --fix handler: wraps the whole init_cmd sub-command; a fix failure is reported and the doctor run continues.
                    console.print(f"[red]Failed to configure telemetry: {exc!s}[/red]")
                console.print()

        # Fix outdated model deck
        if can_fix_deck:
            if Confirm.ask("[bold]Update the model deck now?[/bold]", default=True):
                try:
                    console.print()
                    update_cmd(yes=True)
                    console.print("[green]✓[/green] Model deck updated")
                except Exception as exc:  # noqa: BLE001
                    # Doctor --fix handler: wraps the whole update_cmd sub-command; a fix failure is reported and the doctor run continues.
                    console.print(f"[red]Failed to update deck: {exc!s}[/red]")
                console.print()

        # Fix outdated backend files
        if can_fix_backends and fixable_backends:
            console.print("[bold]Outdated Backend Configuration Files[/bold]")
            console.print()

            for backend_name, backend_file_report in fixable_backends:
                console.print(f"  Backend: [cyan]{backend_name}[/cyan]")
                console.print(f"  File: [dim]{backend_file_report.file_path}[/dim]")
                console.print("  [yellow]⚠[/yellow] Configuration format may be outdated")
                console.print()

                if Confirm.ask("[bold]Replace with latest template from the Pipelex kit?[/bold]", default=True):
                    try:
                        # Derive config_dir from the resolved file path so the fix targets the
                        # same directory where the broken file was found (file lives at
                        # {config_dir}/inference/backends/{name}.toml).
                        resolved_config_dir = Path(backend_file_report.file_path).parent.parent.parent
                        success = replace_backend_file(backend_name, dry_run=False, config_dir=resolved_config_dir)
                        if success:
                            console.print(f"[green]✓[/green] Replaced {backend_name} backend configuration")
                        else:
                            console.print(f"[red]Failed to replace {backend_name}: Template not found or copy failed[/red]")
                    except Exception as exc:  # noqa: BLE001
                        # Doctor --fix handler: wraps replace_backend_file; a fix failure is reported and the doctor run continues.
                        console.print(f"[red]Failed to replace {backend_name}: {exc!s}[/red]")
                    console.print()
                else:
                    console.print(f"[dim]Skipped {backend_name}[/dim]")
                    console.print()

    # Handle issues that can't be auto-fixed
    if has_config_validation_error or has_telemetry_validation_error or has_backend_credential_issues:
        console = get_console()
        console.print("[bold yellow]Manual Fixes Required[/bold yellow]")
        console.print()

        # Config validation errors
        if has_config_validation_error:
            console.print("[bold]Configuration validation error:[/bold]")
            console.print(f"  {config_message}")
            console.print()
            console.print(f"You can fix this manually by editing [cyan]{config_location.config_dir}/pipelex.toml[/cyan]")
            console.print("or run [cyan]pipelex init config[/cyan] to regenerate from template.")
            console.print()

        # Telemetry validation errors (skip if message already contains the fix command)
        if has_telemetry_validation_error and "pipelex init telemetry" not in telemetry_message:
            console.print("[bold]Telemetry validation error:[/bold]")
            console.print(f"  {telemetry_message}")
            console.print()
            console.print(f"You can fix this manually by editing [cyan]{config_location.config_dir}/telemetry.toml[/cyan]")
            console.print("or run [cyan]pipelex init telemetry[/cyan] to regenerate from template.")
            console.print()

        # Backend credentials
        if has_backend_credential_issues:
            all_missing_vars: set[str] = set()
            for backend_report in backend_credential_reports.values():
                if not backend_report.all_credentials_valid:
                    all_missing_vars.update(backend_report.missing_vars)

            if all_missing_vars:
                console.print("[bold]Backend credentials:[/bold]")
                console.print()
                console.print("Set the following environment variables:")
                console.print()

                # Show .env file syntax first
                console.print("[dim]# In your .env file:[/dim]")
                for var_name in sorted(all_missing_vars):
                    console.print(f"{var_name}=[yellow]your_value_here[/yellow]")
                console.print()

                # Show shell syntax for different platforms
                console.print("[dim]# Or in your shell:[/dim]")
                console.print()

                # Linux/MacOS
                console.print("[dim]# Linux/MacOS[/dim]")
                for var_name in sorted(all_missing_vars):
                    console.print(f"export {var_name}=[yellow]your_value_here[/yellow]")
                console.print()

                # Windows PowerShell
                console.print("[dim]# Windows PowerShell[/dim]")
                for var_name in sorted(all_missing_vars):
                    console.print(f'$env:{var_name}="[yellow]your_value_here[/yellow]"')
                console.print()

                # Windows CMD
                console.print("[dim]# Windows CMD[/dim]")
                for var_name in sorted(all_missing_vars):
                    console.print(f"set {var_name}=[yellow]your_value_here[/yellow]")
                console.print()

    sys.exit(1)
