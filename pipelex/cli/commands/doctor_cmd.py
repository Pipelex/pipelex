"""Doctor command for checking Pipelex configuration health."""

from __future__ import annotations

import contextlib
import io
import sys

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from pipelex import log
from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.config import PipelexConfig, get_config
from pipelex.core.validation import report_validation_error
from pipelex.exceptions import PipelexConfigError
from pipelex.hub import PipelexHub, set_pipelex_hub
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryConfig
from pipelex.tools.misc.dict_utils import extract_vars_from_strings_recursive
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.placeholder import value_is_placeholder
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def check_config_files() -> tuple[bool, int, str]:
    """Check if configuration files are present and main config is valid.

    Returns:
        Tuple of (is_healthy, missing_count, message)
    """
    # Check for missing files
    try:
        missing_count = init_config(reset=False, dry_run=True)
    except Exception as exc:
        return False, 0, f"Error checking config files: {exc}"

    # Check if main config can be loaded using the hub's setup
    pipelex_config_path = ".pipelex/pipelex.toml"
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
        except Exception as exc:
            return False, 0, f"Error loading pipelex.toml: {exc}"

    # Report results
    if missing_count == 0:
        return True, 0, "All configuration files present and valid"
    return False, missing_count, f"{missing_count} configuration file(s) missing"


def check_telemetry_config() -> tuple[bool, str]:
    """Check if telemetry configuration is valid.

    Returns:
        Tuple of (is_healthy, message)
    """
    # Use hard-coded path to avoid needing Pipelex initialization
    telemetry_config_path = f".pipelex/{TELEMETRY_CONFIG_FILE_NAME}"

    if not path_exists(telemetry_config_path):
        return False, "Telemetry configuration file not found"

    try:
        toml_doc = load_toml_from_path(telemetry_config_path)
        telemetry_config = TelemetryConfig.model_validate(toml_doc)
        return True, f"Telemetry configured (mode: {telemetry_config.telemetry_mode})"
    except ValidationError as validation_error:
        validation_error_msg = format_pydantic_validation_error(validation_error)
        msg = f"Invalid telemetry configuration: {validation_error_msg}"
        return False, msg
    except Exception as exc:
        return False, f"Error loading telemetry config: {exc}"


def check_backend_credentials() -> tuple[bool, dict[str, BackendCredentialsReport], str]:
    """Check if backend credentials are properly configured.

    Returns:
        Tuple of (is_healthy, backend_reports_dict, summary_message)
    """
    # Use hard-coded path to avoid needing Pipelex initialization
    backends_toml_path = ".pipelex/inference/backends.toml"

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

    except Exception as exc:
        return False, {}, f"Error checking backend credentials: {exc}"


def display_health_report(
    console: Console,
    config_healthy: bool,
    config_message: str,
    config_missing_count: int,
    telemetry_healthy: bool,
    telemetry_message: str,
    backends_healthy: bool,
    backends_message: str,
    backend_reports: dict[str, BackendCredentialsReport],
    models_healthy: bool,
    models_message: str,
) -> None:
    """Display a comprehensive health report.

    Args:
        console: Rich Console instance for output
        config_healthy: Whether config files check passed
        config_message: Message about config files status
        config_missing_count: Number of missing config files
        telemetry_healthy: Whether telemetry check passed
        telemetry_message: Message about telemetry status
        backends_healthy: Whether backends check passed
        backends_message: Message about backends status
        backend_reports: Dict of backend credential reports
        models_healthy: Whether models check passed
        models_message: Message about models status
    """
    all_healthy = config_healthy and telemetry_healthy and backends_healthy and models_healthy

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
    console.print()
    console.print(status_panel)
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
    elif not backend_reports:
        # No backends were checked (e.g., file not found)
        console.print(f"  [red]✗[/red] {backends_message}")
    else:
        console.print(f"  [yellow]⚠[/yellow]  {backends_message}")
        console.print()

        # Show details for each backend
        for backend_name, backend_report in backend_reports.items():
            if backend_report.all_credentials_valid:
                console.print(f"  [dim]{backend_name}[/dim]")
                console.print("    [green]✓[/green] All credentials set")
            else:
                console.print(f"  [bold]{backend_name}[/bold]")
                if backend_report.missing_vars:
                    console.print(f"    [red]✗[/red] Missing: {', '.join(backend_report.missing_vars)}")
                if backend_report.placeholder_vars:
                    console.print(f"    [yellow]⚠[/yellow] Placeholders: {', '.join(backend_report.placeholder_vars)}")
    console.print()

    # Models section
    console.print("[bold]Models[/bold]")
    if models_healthy:
        console.print(f"  [green]✓[/green] {models_message}")
    else:
        console.print(f"  [red]✗[/red] {models_message}")
    console.print()

    # Recommended actions
    if not all_healthy:
        # Check what can be auto-fixed
        can_auto_fix_config = not config_healthy and config_missing_count > 0
        can_auto_fix_telemetry = not telemetry_healthy and "not found" in telemetry_message.lower()
        has_telemetry_validation_error = not telemetry_healthy and "not found" not in telemetry_message.lower()

        # Determine if we have any recommendations to show
        has_recommendations = (
            can_auto_fix_config or can_auto_fix_telemetry or has_telemetry_validation_error or (not backends_healthy and backend_reports)
        )

        if has_recommendations:
            console.print("[bold]Recommended Actions[/bold]")

            if can_auto_fix_config:
                console.print("  • Run [cyan]pipelex init config[/cyan] to install missing configuration files")

            if can_auto_fix_telemetry:
                console.print("  • Run [cyan]pipelex init telemetry[/cyan] to configure telemetry preferences")

            if has_telemetry_validation_error:
                console.print("  • Fix validation errors in [cyan].pipelex/telemetry.toml[/cyan]")
                console.print("    or run [cyan]pipelex init telemetry --reset[/cyan] to regenerate")

            if not backends_healthy and backend_reports:
                # Collect all missing and placeholder vars
                all_missing_vars: set[str] = set()
                all_placeholder_vars: set[str] = set()

                for backend_report in backend_reports.values():
                    if not backend_report.all_credentials_valid:
                        all_missing_vars.update(backend_report.missing_vars)
                        all_placeholder_vars.update(backend_report.placeholder_vars)

                if all_missing_vars:
                    console.print("  • Set the following environment variables:")
                    for var_name in sorted(all_missing_vars):
                        console.print(f"    - {var_name}")

                if all_placeholder_vars:
                    console.print("  • Replace placeholder values for:")
                    for var_name in sorted(all_placeholder_vars):
                        console.print(f"    - {var_name}")

            console.print()

            # Only suggest --fix if there are auto-fixable issues
            if can_auto_fix_config or can_auto_fix_telemetry:
                console.print("[dim]Run[/dim] [cyan]pipelex doctor --fix[/cyan] [dim]to interactively fix auto-fixable issues.[/dim]")
                console.print()

        # Show Discord support for manual-fix issues (regardless of --fix flag)
        has_config_validation_error = not config_healthy and config_missing_count == 0
        has_backend_credential_issues = not backends_healthy and backend_reports
        if has_config_validation_error or has_backend_credential_issues or has_telemetry_validation_error:
            console.print("[dim]If you need help with manual fixes:[/dim]")
            console.print("  [cyan]https://docs.pipelex.com[/cyan] - Documentation")
            console.print("  [cyan]https://go.pipelex.com/discord[/cyan] - Discord Community")
            console.print()


def check_models() -> tuple[bool, str]:
    """Check if models are valid.

    Returns:
        Tuple of (is_healthy, message)
    """
    pipelex_hub = PipelexHub()
    set_pipelex_hub(pipelex_hub)

    # tools
    try:
        pipelex_hub.setup_config(config_cls=PipelexConfig)
    except ValidationError as validation_error:
        validation_error_msg = report_validation_error(category="config", validation_error=validation_error)
        msg = f"Could not setup config because of: {validation_error_msg}"
        raise PipelexConfigError(msg) from validation_error

    log.configure(log_config=get_config().pipelex.log_config)

    models_manager = ModelManager()
    secrets_provider = EnvSecretsProvider()
    try:
        models_manager.setup(secrets_provider=secrets_provider)
        models_manager.validate_model_deck()
    except Exception as exc:
        return False, f"Error checking models: {exc}"
    return True, "Models are valid"


def doctor_cmd(
    fix: bool = False,
) -> None:
    """Check Pipelex configuration health and suggest fixes.

    Args:
        fix: If True, offer to fix detected issues interactively
    """
    console = Console()
    do_doctor_cmd(console=console, fix=fix)
    try:
        do_doctor_cmd(console=console, fix=fix)

    except Exception as exc:
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
    console: Console,
    fix: bool = False,
) -> None:
    """Check Pipelex configuration health and suggest fixes.

    Args:
        console: Rich Console instance for output
        fix: If True, offer to fix detected issues interactively
    """
    # Run health checks
    config_healthy, config_missing_count, config_message = check_config_files()
    telemetry_healthy, telemetry_message = check_telemetry_config()
    backends_healthy, backend_reports, backends_message = check_backend_credentials()
    models_healthy, models_message = check_models()

    # Display report
    display_health_report(
        console=console,
        config_healthy=config_healthy,
        config_message=config_message,
        config_missing_count=config_missing_count,
        telemetry_healthy=telemetry_healthy,
        telemetry_message=telemetry_message,
        backends_healthy=backends_healthy,
        backends_message=backends_message,
        backend_reports=backend_reports,
        models_healthy=models_healthy,
        models_message=models_message,
    )

    all_healthy = config_healthy and telemetry_healthy and backends_healthy and models_healthy

    # Exit code: 0 if healthy, 1 if issues found
    if all_healthy:
        sys.exit(0)

    # Determine what can be auto-fixed
    can_fix_config = not config_healthy and config_missing_count > 0
    can_fix_telemetry = not telemetry_healthy and "not found" in telemetry_message.lower()
    has_auto_fixable_issues = can_fix_config or can_fix_telemetry

    # Determine what requires manual fixes
    has_config_validation_error = not config_healthy and config_missing_count == 0
    has_telemetry_validation_error = not telemetry_healthy and "not found" not in telemetry_message.lower()
    has_backend_credential_issues = not backends_healthy and backend_reports

    # If --fix flag is provided, offer to fix auto-fixable issues
    if fix and has_auto_fixable_issues:
        console.print("[bold yellow]Interactive Fix Mode[/bold yellow]")
        console.print()

        # Fix missing config files
        if can_fix_config:
            if Confirm.ask(f"[bold]Install {config_missing_count} missing configuration file(s)?[/bold]", default=True):
                try:
                    console.print()
                    init_cmd(focus=InitFocus.CONFIG, reset=False, skip_confirmation=True)
                    console.print("[green]✓[/green] Configuration files installed")
                except Exception as exc:
                    console.print(f"[red]Failed to install configuration files: {exc!s}[/red]")
                console.print()

        # Fix missing telemetry config
        if can_fix_telemetry:
            if Confirm.ask("[bold]Configure telemetry preferences?[/bold]", default=True):
                try:
                    console.print()
                    init_cmd(focus=InitFocus.TELEMETRY, reset=False, skip_confirmation=True)
                    console.print("[green]✓[/green] Telemetry configured")
                except Exception as exc:
                    console.print(f"[red]Failed to configure telemetry: {exc!s}[/red]")
                console.print()

    # Handle issues that can't be auto-fixed
    if has_config_validation_error or has_telemetry_validation_error or has_backend_credential_issues:
        console.print("[bold yellow]Manual Fixes Required[/bold yellow]")
        console.print()

        # Config validation errors
        if has_config_validation_error:
            console.print("[bold]Configuration validation error:[/bold]")
            console.print(f"  {config_message}")
            console.print()
            console.print("You can fix this manually by editing [cyan].pipelex/pipelex.toml[/cyan]")
            console.print("or run [cyan]pipelex init config --reset[/cyan] to regenerate from template.")
            console.print()

        # Telemetry validation errors
        if has_telemetry_validation_error:
            console.print("[bold]Telemetry validation error:[/bold]")
            console.print(f"  {telemetry_message}")
            console.print()
            console.print("You can fix this manually by editing [cyan].pipelex/telemetry.toml[/cyan]")
            console.print("or run [cyan]pipelex init telemetry --reset[/cyan] to regenerate from template.")
            console.print()

        # Backend credentials
        if has_backend_credential_issues:
            all_missing_vars: set[str] = set()
            for backend_report in backend_reports.values():
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
