from typing import NoReturn

import typer

from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import get_console
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipeline.validate_bundle import ValidateBundleError
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTermsNotAcceptedError,
    RemoteConfigFetchError,
    RemoteConfigValidationError,
)
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
    VALIDATION_BEFORE_BUILD_PIPE = "Pre-validation (build pipe)"
    VALIDATION_BEFORE_BUILD_RUNNER = "Pre-validation (build runner)"
    VALIDATION_BEFORE_BUILD_INPUTS = "Pre-validation (build inputs)"


def handle_model_choice_error(exc: PipeOperatorModelChoiceError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelChoiceError with formatted output.

    Args:
        exc: The model choice error exception
        context: Context for the error message
    """
    console = get_console()
    console.print(f"\n[bold red]❌ {context} failed because of a model choice could not be interpreted correctly[/bold red]\n")
    console.print(f"[bold cyan]Pipe:[/bold cyan]         [yellow]'{exc.pipe_code}'[/yellow] [dim]({exc.pipe_type})[/dim]")
    console.print(f"[bold cyan]Model Type:[/bold cyan]   [yellow]'{exc.model_type}'[/yellow]")
    console.print(f"[bold cyan]Model Choice:[/bold cyan] [yellow]'{exc.model_choice}'[/yellow]")
    console.print(f"\n[bold red]Error:[/bold red]        {exc.message}\n")
    console.print(
        f"[bold green]💡 Tip:[/bold green] Check your model configuration in [cyan].pipelex/inference/[/cyan] "
        f"or specify a different model in the [yellow]'{exc.pipe_code}'[/yellow] pipe."
    )
    console.print(f"[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_model_availability_error(exc: PipeOperatorModelAvailabilityError, context: ErrorContext) -> NoReturn:
    """Handle and display PipeOperatorModelAvailabilityError with formatted output.

    Args:
        exc: The model availability error exception
        context: Context for the error message
    """
    console = get_console()
    console.print(f"\n[bold red]❌ {context} failed because a model wasn't available[/bold red]\n")
    console.print(f"[bold cyan]Pipe:[/bold cyan]         [yellow]'{exc.pipe_code}'[/yellow] [dim]({exc.pipe_type})[/dim]")
    console.print(f"[bold cyan]Model:[/bold cyan]        [yellow]'{exc.model_handle}'[/yellow]")
    if exc.fallback_list:
        fallbacks_str = ", ".join([f"[yellow]{fb}[/yellow]" for fb in exc.fallback_list])
        console.print(f"[bold cyan]Fallbacks:[/bold cyan]    {fallbacks_str}")
    if len(exc.pipe_stack) > 1:
        stack_str = " [dim]→[/dim] ".join([f"[yellow]{p}[/yellow]" for p in exc.pipe_stack])
        console.print(f"[bold cyan]Pipe Stack:[/bold cyan]   {stack_str}")
    console.print(f"\n[bold red]Error:[/bold red]        {exc}\n")
    console.print(
        f"[bold green]💡 Tip:[/bold green] Check your model configuration in [cyan].pipelex/inference/[/cyan] "
        f"or specify a different model in the [yellow]'{exc.pipe_code}'[/yellow] pipe."
    )
    console.print(f"[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_model_deck_preset_error(exc: ModelDeckPresetValidatonError, context: ErrorContext) -> NoReturn:
    """Handle and display ModelDeckPresetValidatonError with formatted output.

    Args:
        exc: The model deck preset validation error exception
        context: Context for the error message
    """
    console = get_console()
    console.print(f"\n[bold red]❌ {context} failed due to model deck preset validation error[/bold red]\n")
    console.print(f"[bold cyan]Preset ID:[/bold cyan]    [yellow]'{exc.preset_id}'[/yellow]")
    console.print(f"[bold cyan]Model Type:[/bold cyan]   [yellow]'{exc.model_type}'[/yellow]")
    console.print(f"[bold cyan]Model Handle:[/bold cyan] [yellow]'{exc.model_handle}'[/yellow]")
    if exc.enabled_backends:
        backends_str = ", ".join([f"[yellow]{b}[/yellow]" for b in sorted(exc.enabled_backends)])
        console.print(f"[bold cyan]Enabled Backends:[/bold cyan] {backends_str}")
    console.print(f"\n[bold red]Error:[/bold red]        {exc.message}\n")
    backends_str = ", ".join([f"[yellow]{b}[/yellow]" for b in sorted(exc.enabled_backends)])
    console.print(
        f"[bold green]💡 Tip:[/bold green] The preset [yellow]'{exc.preset_id}'[/yellow] references model handle "
        f"[yellow]'{exc.model_handle}'[/yellow] which is not available in any enabled backend.\n"
        f"The enabled backends are: {backends_str}."
    )
    console.print(
        "[bold]Possible solutions:[/bold]\n"
        "  1. Update the preset to use a different model\n"
        f"  2. Configure model '{exc.model_handle}' in one of your enabled backends\n"
        f"  3. Enable a backend that supports [yellow]'{exc.model_handle}'[/yellow]"
    )
    console.print(f"\n[dim]Learn more about the inference backend system: {URLs.backend_provider_docs}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc


def handle_validate_bundle_error(exc: ValidateBundleError, bundle_path: str | None = None) -> NoReturn:
    """Handle and display ValidateBundleError with formatted output.

    Args:
        exc: The bundle validation error exception
        bundle_path: Optional path to the bundle file being validated
    """
    console = get_console()
    console.print("\n[bold red]❌ Bundle validation failed[/bold red]\n")

    if bundle_path:
        console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{bundle_path}[/yellow]\n")

    # Display blueprint validation errors (e.g., MISSING_INPUT_VARIABLE, EXTRANEOUS_INPUT_VARIABLE from blueprint validation)
    if exc.pipelex_bundle_blueprint_validation_errors:
        console.print("[bold cyan]Blueprint Validation Errors:[/bold cyan]\n")
        for error_index, blueprint_error in enumerate(exc.pipelex_bundle_blueprint_validation_errors, 1):
            error_type_display = blueprint_error.error_type.replace("_", " ").title() if blueprint_error.error_type else "Validation Error"
            console.print(f"[bold yellow]{error_index}. {error_type_display}[/bold yellow]")

            # Display key identification info
            if blueprint_error.pipe_code:
                console.print(f"   [cyan]Pipe:[/cyan] [yellow]{blueprint_error.pipe_code}[/yellow]")
            if blueprint_error.domain_code:
                console.print(f"   [cyan]Domain:[/cyan] [green]{blueprint_error.domain_code}[/green]")

            # Variables
            if blueprint_error.variable_names:
                variables_str = ", ".join([f"[yellow]{v}[/yellow]" for v in blueprint_error.variable_names])
                console.print(f"   [cyan]Variables:[/cyan] {variables_str}")

            # Error message
            console.print(f"   [cyan]→[/cyan] {blueprint_error.message}")

            # Source file
            if blueprint_error.source:
                console.print(f"   [dim]└─ Source: {blueprint_error.source}[/dim]")

            console.print()

    # Display pipe validation errors
    if exc.pipe_validation_error_data:
        console.print("[bold cyan]Pipe Validation Errors:[/bold cyan]\n")
        for pipe_index, pipe_error in enumerate(exc.pipe_validation_error_data, 1):
            console.print(f"[bold yellow]{pipe_index}. {pipe_error.error_type.replace('_', ' ').title()}[/bold yellow]")

            # Display key identification info
            if pipe_error.pipe_code:
                console.print(f"   [cyan]Pipe:[/cyan] [yellow]{pipe_error.pipe_code}[/yellow]")
            if pipe_error.concept_code:
                console.print(f"   [cyan]Concept:[/cyan] [yellow]{pipe_error.concept_code}[/yellow]")
            if pipe_error.domain_code:
                console.print(f"   [cyan]Domain:[/cyan] [green]{pipe_error.domain_code}[/green]")

            # Field name if present
            if pipe_error.field_name:
                console.print(f"   [cyan]Field:[/cyan] [yellow]{pipe_error.field_name}[/yellow]")

            # Variables
            if pipe_error.variable_names:
                variables_str = ", ".join([f"[yellow]{v}[/yellow]" for v in pipe_error.variable_names])
                console.print(f"   [cyan]Variables:[/cyan] {variables_str}")

            # Error message
            console.print(f"   [cyan]→[/cyan] {pipe_error.message}")

            # Field path as secondary info
            if pipe_error.field_path:
                console.print(f"   [dim]└─ Path: {pipe_error.field_path}[/dim]")

            console.print()

    # Display dry run error message
    if exc.dry_run_error_message:
        console.print("[bold cyan]Dry Run Error:[/bold cyan]\n")
        console.print(f"[yellow]{exc.dry_run_error_message}[/yellow]\n")

    # Display helpful tips
    console.print(
        "[bold green]💡 Tip:[/bold green] Review the error messages above and check your pipeline configuration. "
        "Make sure all required fields are present and correctly formatted."
    )
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
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


def handle_remote_config_fetch_error(exc: RemoteConfigFetchError) -> NoReturn:
    """Handle and display RemoteConfigFetchError with user-friendly guidance.

    This error occurs when Pipelex Gateway is enabled but the remote configuration
    cannot be fetched (network issues, server unreachable, etc.).

    Args:
        exc: The remote config fetch error exception
    """
    console = get_console()
    console.print("\n[bold red]❌ Could not connect to Pipelex Gateway[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Network Issue:[/bold yellow] Pipelex Gateway requires network access to fetch\n"
        "configuration, but we couldn't reach the Pipelex servers.\n"
    )

    console.print("[bold cyan]Error details:[/bold cyan]")
    console.print(f"  {exc}\n")

    console.print("[bold green]💡 To fix:[/bold green]")
    console.print("  • Check your internet connection")
    console.print("  • Verify that firewall/proxy settings allow outbound HTTPS requests")
    console.print("  • Try again in a few moments (servers may be temporarily unavailable)")
    console.print()

    console.print("[dim]Alternatively, you can:[/dim]")
    console.print("[dim]  • Disable pipelex_gateway in .pipelex/inference/backends.toml[/dim]")
    console.print("[dim]  • Use your own API keys with direct provider backends[/dim]")
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
    console.print("\n[bold red]❌ Pipelex Gateway configuration is invalid[/bold red]\n")

    console.print(
        "[bold yellow]⚠ Server Issue:[/bold yellow] The Pipelex Gateway configuration was received but\n"
        "couldn't be validated. This is a server-side issue that we need to fix.\n"
    )

    console.print("[bold cyan]Error details:[/bold cyan]")
    console.print(f"  {exc}\n")

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
