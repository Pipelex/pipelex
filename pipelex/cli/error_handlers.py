from pathlib import Path
from typing import NoReturn

import click
import typer
from rich.console import Console
from rich.markup import escape
from rich.traceback import Traceback

from pipelex.cogt.exceptions import GatewayUnknownModelError, ModelDeckPresetValidatonError
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import get_console
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipeline.validate_bundle import ValidateBundleError
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    InferenceSetupRequiredError,
    RemoteConfigUnavailableError,
    RemoteConfigValidationError,
)
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.types import StrEnum
from pipelex.urls import URLs


class ErrorContext(StrEnum):
    """Context for error messages in CLI commands."""

    PIPE_RUN = "Pipe run"
    VALIDATION = "Pipe validation"
    BUILD = "Pipe build"

    # Pre-validation contexts (for Pipelex.make() errors)
    VALIDATION_BEFORE_SHOW_PIPES = "Pre-validation (show pipes)"
    VALIDATION_BEFORE_SHOW_PIPE = "Pre-validation (show pipe)"
    VALIDATION_BEFORE_SHOW_MODELS = "Pre-validation (show models)"
    VALIDATION_BEFORE_SHOW_BACKENDS = "Pre-validation (show backends)"
    VALIDATION_BEFORE_PIPE_RUN = "Pre-validation (pipe run)"
    VALIDATION_BEFORE_BUILD_RUNNER = "Pre-validation (build runner)"
    VALIDATION_BEFORE_BUILD_INPUTS = "Pre-validation (build inputs)"
    VALIDATION_BEFORE_BUILD_OUTPUT = "Pre-validation (build output)"
    KIT = "Kit operation"


def is_traceback_requested() -> bool:
    """Check whether the --traceback global flag was passed on the CLI invocation."""
    try:
        ctx = click.get_current_context(silent=True)
    except RuntimeError:
        return False
    if ctx is None:
        return False
    obj = ctx.find_root().obj
    if obj is None:
        return False
    return bool(obj.get("traceback", False))


def print_traceback_if_requested(console: Console) -> None:
    """Print a Rich traceback of the current exception when --traceback is active."""
    if is_traceback_requested():
        console.print(Traceback())


def display_error_panel(
    console: Console,
    *,
    title: str,
    fields: list[tuple[str, str]],
    error_message: str | None,
    tip: str,
    links: list[tuple[str, str]],
) -> None:
    """Print the canonical CLI error panel.

    Layout: a red ❌ banner, an aligned block of structured fields, the error
    message, a 💡 tip, and dimmed help links. Field labels are right-padded to
    a common width so the values line up.

    Exception-specific logic (which fields to include, what tip to derive)
    stays in each ``handle_*`` function; this helper owns only the panel shape.

    Args:
        console: Rich console to print to.
        title: Headline text after the ❌ (already markup-safe).
        fields: ``(label, value)`` pairs; values must already be escaped.
        error_message: The error message body, or None to omit it.
        tip: The 💡 tip text (may span multiple lines / carry markup).
        links: ``(label, url)`` pairs printed dimmed at the bottom.
    """
    console.print(f"\n[bold red]❌ {title}[/bold red]\n")
    label_width = max((len(label) for label, _ in fields), default=0)
    for label, value in fields:
        padded_label = f"{label}:".ljust(label_width + 1)
        console.print(f"[bold cyan]{padded_label}[/bold cyan] {value}")
    if error_message is not None:
        console.print(f"\n[bold red]Error:[/bold red] {error_message}\n")
    console.print(f"[bold green]💡 Tip:[/bold green] {tip}")
    for link_label, link_url in links:
        console.print(f"[dim]{link_label}: {link_url}[/dim]")
    console.print()


def handle_model_choice_error(exc: PipeOperatorModelChoiceError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelChoiceError with formatted output.

    Args:
        exc: The model choice error exception
        context: Context for the error message
    """
    console = get_console()
    print_traceback_if_requested(console)
    report = exc.to_error_report()
    tip = report.user_action_detail() or (
        f"Check your model configuration in .pipelex/inference/ or specify a different model in the '{exc.pipe_code}' pipe."
    )
    display_error_panel(
        console,
        title=f"{context} failed because of a model choice could not be interpreted correctly",
        fields=[
            ("Pipe", f"[yellow]'{escape(exc.pipe_code)}'[/yellow] [dim]({escape(exc.pipe_type)})[/dim]"),
            ("Model Type", f"[yellow]'{escape(exc.model_type)}'[/yellow]"),
            ("Model Choice", f"[yellow]'{escape(str(exc.model_choice))}'[/yellow]"),
        ],
        error_message=escape(exc.message),
        tip=escape(tip),
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(1) from exc


def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelAvailabilityError with formatted output.

    Args:
        exc: The model availability error exception
        context: Context for the error message
    """
    console = get_console()
    print_traceback_if_requested(console)
    report = exc.to_error_report()
    fields: list[tuple[str, str]] = [
        ("Pipe", f"[yellow]'{escape(exc.pipe_code)}'[/yellow] [dim]({escape(exc.pipe_type)})[/dim]"),
        ("Model", f"[yellow]'{escape(exc.model_handle or '')}'[/yellow]"),
    ]
    if exc.fallback_list:
        fallbacks_str = ", ".join([f"[yellow]{escape(fallback)}[/yellow]" for fallback in exc.fallback_list])
        fields.append(("Fallbacks", fallbacks_str))
    if len(exc.pipe_stack) > 1:
        stack_str = " [dim]→[/dim] ".join([f"[yellow]{escape(stacked_pipe)}[/yellow]" for stacked_pipe in exc.pipe_stack])
        fields.append(("Pipe Stack", stack_str))
    tip = report.user_action_detail() or (
        f"Check your model configuration in .pipelex/inference/ or specify a different model in the '{exc.pipe_code}' pipe."
    )
    display_error_panel(
        console,
        title=f"{context} failed because a model wasn't available",
        fields=fields,
        error_message=escape(str(exc)),
        tip=escape(tip),
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(1) from exc


def handle_model_deck_preset_error(exc: ModelDeckPresetValidatonError, context: ErrorContext) -> NoReturn:
    """Handle and display ModelDeckPresetValidatonError with formatted output.

    Args:
        exc: The model deck preset validation error exception
        context: Context for the error message
    """
    console = get_console()
    print_traceback_if_requested(console)
    report = exc.to_error_report()
    model_handle = exc.model_handle or ""
    fields: list[tuple[str, str]] = [
        ("Preset ID", f"[yellow]'{escape(exc.preset_id)}'[/yellow]"),
        ("Model Type", f"[yellow]'{escape(exc.model_type)}'[/yellow]"),
        ("Model Handle", f"[yellow]'{escape(model_handle)}'[/yellow]"),
    ]
    if exc.enabled_backends:
        backends_str = ", ".join([f"[yellow]{escape(backend)}[/yellow]" for backend in sorted(exc.enabled_backends)])
        fields.append(("Enabled Backends", backends_str))

    tip_detail = report.user_action_detail()
    if tip_detail is not None:
        tip = escape(tip_detail)
    else:
        tip_lines: list[str] = [
            (
                f"The preset [yellow]'{escape(exc.preset_id)}'[/yellow] references model handle "
                f"[yellow]'{escape(model_handle)}'[/yellow] which is not available in any enabled backend."
            )
        ]
        if exc.enabled_backends:
            backends_str = ", ".join([f"[yellow]{escape(backend)}[/yellow]" for backend in sorted(exc.enabled_backends)])
            tip_lines.append(f"The enabled backends are: {backends_str}.")
        tip_lines.append(
            "[bold]Possible solutions:[/bold]\n"
            "  1. Update the preset to use a different model\n"
            f"  2. Configure model '{escape(model_handle)}' in one of your enabled backends\n"
            f"  3. Enable a backend that supports [yellow]'{escape(model_handle)}'[/yellow]"
        )
        tip = "\n".join(tip_lines)

    display_error_panel(
        console,
        title=f"{context} failed due to model deck preset validation error",
        fields=fields,
        error_message=escape(exc.message),
        tip=tip,
        links=[
            ("Learn more about the inference backend system", URLs.backend_provider_docs),
            ("Join our Discord for help", URLs.discord),
        ],
    )
    raise typer.Exit(1) from exc


def _display_validation_error_details(console: Console, exc: ValidateBundleError) -> None:
    """Display the detailed validation error information from a ValidateBundleError.

    Args:
        console: Rich console instance to print to
        exc: The bundle validation error exception
    """
    # Display blueprint validation errors (e.g., MISSING_INPUT_VARIABLE, EXTRANEOUS_INPUT_VARIABLE from blueprint validation)
    if exc.pipelex_bundle_blueprint_validation_errors:
        console.print("[bold cyan]Blueprint Validation Errors:[/bold cyan]\n")
        for error_index, blueprint_error in enumerate(exc.pipelex_bundle_blueprint_validation_errors, 1):
            error_type_display = blueprint_error.error_type.replace("_", " ").title() if blueprint_error.error_type else "Validation Error"
            console.print(f"[bold yellow]{error_index}. {error_type_display}[/bold yellow]")

            # Display key identification info
            if blueprint_error.pipe_code:
                console.print(f"   [cyan]Pipe:[/cyan] [yellow]{escape(blueprint_error.pipe_code)}[/yellow]")
            if blueprint_error.domain_code:
                console.print(f"   [cyan]Domain:[/cyan] [green]{escape(blueprint_error.domain_code)}[/green]")

            # Variables
            if blueprint_error.variable_names:
                variables_str = ", ".join([f"[yellow]{escape(v)}[/yellow]" for v in blueprint_error.variable_names])
                console.print(f"   [cyan]Variables:[/cyan] {variables_str}")

            # Error message
            console.print(f"   [cyan]→[/cyan] {escape(blueprint_error.message)}")

            # Source file
            if blueprint_error.source:
                console.print(f"   [dim]└─ Source: {escape(blueprint_error.source)}[/dim]")

            console.print()

    # Display pipe validation errors
    if exc.pipe_validation_error_data:
        console.print("[bold cyan]Pipe Validation Errors:[/bold cyan]\n")
        for pipe_index, pipe_error in enumerate(exc.pipe_validation_error_data, 1):
            console.print(f"[bold yellow]{pipe_index}. {pipe_error.error_type.replace('_', ' ').title()}[/bold yellow]")

            # Display key identification info
            if pipe_error.pipe_code:
                console.print(f"   [cyan]Pipe:[/cyan] [yellow]{escape(pipe_error.pipe_code)}[/yellow]")
            if pipe_error.concept_code:
                console.print(f"   [cyan]Concept:[/cyan] [yellow]{escape(pipe_error.concept_code)}[/yellow]")
            if pipe_error.domain_code:
                console.print(f"   [cyan]Domain:[/cyan] [green]{escape(pipe_error.domain_code)}[/green]")

            # Field name if present
            if pipe_error.field_name:
                console.print(f"   [cyan]Field:[/cyan] [yellow]{escape(pipe_error.field_name)}[/yellow]")

            # Variables
            if pipe_error.variable_names:
                variables_str = ", ".join([f"[yellow]{escape(v)}[/yellow]" for v in pipe_error.variable_names])
                console.print(f"   [cyan]Variables:[/cyan] {variables_str}")

            # Error message
            console.print(f"   [cyan]→[/cyan] {escape(pipe_error.message)}")

            # Field path as secondary info
            if pipe_error.field_path:
                console.print(f"   [dim]└─ Path: {escape(pipe_error.field_path)}[/dim]")

            console.print()

    # Display dry run error message
    if exc.dry_run_error_message:
        console.print("[bold cyan]Dry Run Error:[/bold cyan]\n")
        console.print(f"[yellow]{escape(exc.dry_run_error_message)}[/yellow]\n")


def handle_validate_bundle_error(exc: ValidateBundleError, bundle_path: Path | None = None) -> NoReturn:
    """Handle and display ValidateBundleError with formatted output.

    Args:
        exc: The bundle validation error exception
        bundle_path: Optional path to the bundle file being validated
    """
    report = exc.to_error_report()
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Bundle validation failed[/bold red]\n")

    if bundle_path:
        console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]\n")

    _display_validation_error_details(console=console, exc=exc)

    # Display helpful tips
    tip = report.user_action_detail() or (
        "Review the error messages above and check your pipeline configuration. Make sure all required fields are present and correctly formatted."
    )
    console.print(f"[bold green]💡 Tip:[/bold green] {escape(tip)}")
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_inference_setup_required_error(exc: InferenceSetupRequiredError) -> NoReturn:
    """Handle and display InferenceSetupRequiredError with first-run guidance.

    This error occurs on first run when no inference backend has been configured yet.

    Args:
        exc: The inference setup required error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold yellow]⚠ First-time inference setup required[/bold yellow]\n")

    console.print(
        "This looks like your first time running a method with live inference.\nYou need to configure an inference backend before running.\n"
    )

    console.print("[bold green]💡 To get started:[/bold green]")
    console.print("  • Run [cyan]pipelex init config[/cyan] for interactive setup")
    console.print("  • Or run [cyan]pipelex-agent init[/cyan] with backend configuration")
    console.print()

    console.print(f"[dim]For more information: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_telemetry_config_validation_error(exc: TelemetryConfigValidationError) -> NoReturn:
    """Handle and display TelemetryConfigValidationError with migration guidance.

    This error typically occurs when users have an old telemetry.toml format
    that doesn't match the new nested structure.

    Args:
        exc: The telemetry config validation error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Telemetry configuration format has changed[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Breaking Change:[/bold yellow] The telemetry.toml format has been updated.\n"
        "Your existing configuration uses the old flat format.\n"
    )

    console.print("[bold green]💡 To fix:[/bold green] Run [cyan]pipelex init telemetry[/cyan] to create a new config\n")

    console.print("[dim]This update brings powerful new telemetry options:[/dim]")
    console.print("[dim]  • Langfuse integration for LLM observability[/dim]")
    console.print("[dim]  • Support for any OpenTelemetry backend via OTLP exporters[/dim]")
    console.print("[dim]  • Cleaner separation of PostHog, Langfuse, and OTLP settings[/dim]")
    console.print()

    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_gateway_terms_not_accepted_error(exc: GatewayTermsNotAcceptedError) -> NoReturn:
    """Handle and display GatewayTermsNotAcceptedError with user-friendly guidance.

    This error occurs when Pipelex Gateway is enabled but the user hasn't
    accepted the terms of service yet.

    Args:
        exc: The gateway terms not accepted error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Pipelex Gateway terms not accepted[/bold red]\n")

    console.print("[bold yellow]⚠ Action Required:[/bold yellow] Pipelex Gateway is enabled but you haven't accepted\nthe terms of service yet.\n")

    console.print("[bold green]💡 To fix:[/bold green] Run [cyan]pipelex init config[/cyan] to configure your backends and accept the terms\n")

    console.print("[dim]Alternatively, you can:[/dim]")
    console.print("[dim]  • Disable pipelex_gateway in .pipelex/inference/backends.toml[/dim]")
    console.print("[dim]  • Use your own API keys with direct provider backends[/dim]")
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_gateway_api_key_missing_error(exc: GatewayApiKeyMissingError) -> NoReturn:
    """Handle and display GatewayApiKeyMissingError with user-friendly guidance.

    This error occurs when Pipelex Gateway is enabled but the PIPELEX_GATEWAY_API_KEY
    environment variable is not set.

    Args:
        exc: The gateway API key missing error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Pipelex Gateway API key not set[/bold red]\n")

    console.print("[bold yellow]⚠ Action Required:[/bold yellow] Pipelex Gateway is enabled but the API key\nenvironment variable is not set.\n")

    console.print("[bold green]💡 To fix:[/bold green]")
    console.print(f"  • Get your API key at: [cyan]{URLs.app}[/cyan]")
    console.print("  • Set the [cyan]PIPELEX_GATEWAY_API_KEY[/cyan] environment variable")
    console.print()

    console.print("[dim]Alternatively, you can:[/dim]")
    console.print("[dim]  • Disable pipelex_gateway in .pipelex/inference/backends.toml[/dim]")
    console.print("[dim]  • Use your own API keys with direct provider backends[/dim]")
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_gateway_do_not_track_conflict_error(exc: GatewayDoNotTrackConflictError) -> NoReturn:
    """Handle and display GatewayDoNotTrackConflictError with user-friendly guidance.

    This error occurs when Pipelex Gateway is enabled but the user has set
    a DO_NOT_TRACK environment variable, which conflicts with gateway's telemetry requirement.

    Args:
        exc: The gateway do not track conflict error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Pipelex Gateway requires telemetry[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Conflict:[/bold yellow] Pipelex Gateway requires telemetry for service monitoring,\n"
        "but you have set DO_NOT_TRACK. We respect your privacy preference.\n"
    )

    console.print("[bold green]💡 To fix, choose one option:[/bold green]")
    console.print("  • [cyan]Unset[/cyan] the DO_NOT_TRACK environment variable to use Gateway")
    console.print("  • [cyan]Or[/cyan] disable pipelex_gateway in .pipelex/inference/backends.toml")
    console.print("    and use your own API keys with direct provider backends")
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_remote_config_validation_error(exc: RemoteConfigValidationError) -> NoReturn:
    """Handle and display RemoteConfigValidationError with user-friendly guidance.

    This error occurs when Pipelex Gateway remote configuration was fetched but
    the data is malformed or doesn't match the expected schema.

    Args:
        exc: The remote config validation error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Pipelex Gateway configuration is invalid[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Server Issue:[/bold yellow] The Pipelex Gateway configuration was received but\n"
        "couldn't be validated. This is a server-side issue that we need to fix.\n"
    )

    console.print("[bold cyan]Error details:[/bold cyan]")
    console.print(f"  {escape(str(exc))}\n")

    console.print("[bold red]🚨 Please report this![/bold red]")
    console.print("  This error shouldn't happen and we want to fix it ASAP.")
    console.print("  Please copy-paste this error to:")
    console.print(f"  • Discord: [cyan]{URLs.discord}[/cyan]")
    console.print(f"  • GitHub Issues: [cyan]{URLs.repository}/issues[/cyan]")
    console.print()

    console.print("[dim]In the meantime, you can:[/dim]")
    console.print("[dim]  • Disable pipelex_gateway in .pipelex/inference/backends.toml[/dim]")
    console.print("[dim]  • Use your own API keys with direct provider backends[/dim]")
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_remote_config_unavailable_error(exc: RemoteConfigUnavailableError) -> NoReturn:
    """Handle and display RemoteConfigUnavailableError with user-friendly guidance.

    Raised when a fresh fetch failed AND no usable cached fallback exists. The gateway
    is enabled but we have neither network nor a primed local cache.

    Args:
        exc: The remote config unavailable error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Pipelex Gateway is unreachable and no cached config is available[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Offline + Cold Cache:[/bold yellow] Pipelex Gateway requires a config\n"
        "either fetched fresh or restored from a local cache, but neither is available.\n"
    )

    console.print("[bold cyan]Error details:[/bold cyan]")
    console.print(f"  {escape(str(exc))}\n")

    console.print("[bold green]💡 To fix:[/bold green]")
    console.print("  • Reconnect to the network and run [cyan]pipelex init[/cyan] to prime the cache")
    console.print(
        "  • Or disable [cyan]pipelex_gateway[/cyan] in [cyan].pipelex/inference/backends.toml[/cyan] for permanent offline (BYOK) operation"
    )
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_gateway_unknown_model_error(exc: GatewayUnknownModelError) -> NoReturn:
    """Handle and display GatewayUnknownModelError with user-friendly guidance.

    Raised when the active model deck references a gateway model handle that doesn't exist
    in the gateway specs (either freshly fetched or loaded from cache). Branches the
    remediation on the provenance of the gateway config.

    Args:
        exc: The gateway unknown model error exception
    """
    console = get_console()
    print_traceback_if_requested(console)
    console.print("\n[bold red]❌ Unknown gateway model handle[/bold red]\n")

    console.print(f"[bold cyan]Model handle:[/bold cyan] [yellow]'{escape(exc.model_name)}'[/yellow]")
    console.print(f"[bold cyan]Config source:[/bold cyan] [yellow]{escape(exc.source)}[/yellow]")
    console.print(f"\n[bold red]Error:[/bold red] {escape(str(exc))}\n")

    console.print("[bold green]💡 To fix:[/bold green]")
    match exc.source:
        case RemoteConfigSource.FRESH:
            console.print("  • Check the model handle for typos against [cyan]pipelex doctor[/cyan]")
            console.print("  • Update the deck to reference a model the gateway currently exposes")
            console.print("  • Or disable [cyan]pipelex_gateway[/cyan] in [cyan].pipelex/inference/backends.toml[/cyan] to fall back to BYOK")
        case RemoteConfigSource.CACHED:
            console.print("  • The on-disk cache may be stale — run [cyan]pipelex init[/cyan] while online to refresh it")
            console.print("  • Or disable [cyan]pipelex_gateway[/cyan] in [cyan].pipelex/inference/backends.toml[/cyan] to operate offline (BYOK)")
    console.print()

    console.print(f"[dim]For more information: {URLs.gateway_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc
