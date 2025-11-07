from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, cast

import typer
from posthog import tag
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import pretty_print
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_deck_preset_error,
    handle_validation_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.cogt.model_backends.model_lists import ModelLister
from pipelex.config import ConfigPaths
from pipelex.exceptions import LibraryLoadingError, PipelexCLIError, PipelexConfigError
from pipelex.hub import get_models_manager, get_pipe_library, get_required_pipe, get_secrets_provider, get_telemetry_manager
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pipelex.cogt.models.model_manager import ModelManager

COMMAND = "show"
SUB_COMMAND_PIPES = "pipes"
SUB_COMMAND_PIPE = "pipe"
SUB_COMMAND_MODELS = "models"
SUB_COMMAND_BACKENDS = "backends"


def do_show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(final_config, title="Pipelex configuration")
    except Exception as exc:
        msg = f"Error loading configuration: {exc}"
        raise PipelexConfigError(msg) from exc


def do_list_pipes() -> None:
    """List all available pipes."""
    try:
        nb_pipes = get_pipe_library().pretty_list_pipes()
        get_telemetry_manager().track_event(EventName.PIPES_LIST, properties={EventProperty.NB_PIPES: nb_pipes})
    except Exception as exc:
        msg = f"Failed to list pipes: {exc}"
        raise PipelexCLIError(msg) from exc


def do_show_pipe(pipe_code: str) -> None:
    """Show a single pipe definition from the library."""
    pipe = get_required_pipe(pipe_code=pipe_code)
    get_telemetry_manager().track_event(EventName.PIPE_SHOW, properties={EventProperty.PIPE_TYPE: pipe.type})
    pretty_print(pipe, title=f"Pipe '{pipe_code}'")


def do_show_backends(show_all: bool = False) -> None:
    """Display all backends and the active routing profile."""
    try:
        secrets_provider = get_secrets_provider()
        models_manager = cast("ModelManager", get_models_manager())

        # Load backends with or without disabled ones based on show_all flag
        if show_all:
            backend_library = InferenceBackendLibrary()
            backend_library.load(
                secrets_provider=secrets_provider,
                backends_library_path=ConfigPaths.BACKENDS_FILE_PATH,
                backends_dir_path=ConfigPaths.BACKENDS_DIR_PATH,
                include_disabled=True,
            )
        else:
            backend_library = models_manager.inference_backend_library

        routing_profile = models_manager.routing_profile
    except Exception as exc:
        msg = f"Error accessing backend or routing configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    console = Console()

    # Get all backends
    all_backends = list(backend_library.root.values())
    if not all_backends:
        console.print("[yellow]No backends configured.[/yellow]")
        return

    # Filter backends based on show_all flag
    backends_to_display = all_backends if show_all else [b for b in all_backends if b.enabled]

    # Display backends table
    table_title = "All Configured Backends" if show_all else "Enabled Backends"
    backends_table = Table(
        title=table_title,
        show_header=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    backends_table.add_column("Backend Name", style="green")
    if show_all:
        backends_table.add_column("Status", style="yellow")
    backends_table.add_column("Endpoint", style="blue")
    backends_table.add_column("Models", style="cyan", justify="right")

    for backend in sorted(backends_to_display, key=lambda b: b.name):
        endpoint = backend.endpoint if backend.endpoint else "[dim]N/A[/dim]"
        model_count = str(len(backend.model_specs))

        if show_all:
            status = "[green]Enabled[/green]" if backend.enabled else "[red]Disabled[/red]"
            backends_table.add_row(backend.name, status, endpoint, model_count)
        else:
            backends_table.add_row(backend.name, endpoint, model_count)

    console.print("\n")
    console.print(backends_table)
    console.print("\n")

    # Display routing profile information
    try:
        console.print(f"[bold cyan]Active Routing Profile:[/bold cyan] [green]{routing_profile.name}[/green]")
        if routing_profile.description:
            console.print(f"[dim]{routing_profile.description}[/dim]")

        if routing_profile.default:
            console.print(f"[bold]Default Backend:[/bold] [cyan]{routing_profile.default}[/cyan]")

        # Display routing rules
        if routing_profile.routes:
            console.print("\n[bold]Routing Rules:[/bold]")
            routes_table = Table(
                show_header=True,
                header_style="bold cyan",
                box=box.SIMPLE,
                show_edge=False,
            )
            routes_table.add_column("Pattern", style="green")
            routes_table.add_column("→", style="dim", justify="center")
            routes_table.add_column("Target Backend", style="cyan")

            for pattern, target_backend in sorted(routing_profile.routes.items()):
                routes_table.add_row(pattern, "→", target_backend)

            console.print(routes_table)
        else:
            console.print("[dim]No specific routing rules defined.[/dim]")

    except Exception as exc:
        console.print(f"[yellow]Warning: Could not load routing profile information: {exc}[/yellow]")

    console.print("\n")

    # Display helper messages
    if not show_all:
        enabled_count = len([b for b in all_backends if b.enabled])
        disabled_count = len(all_backends) - enabled_count
        if disabled_count > 0:
            console.print(f"[dim]💡 Showing {enabled_count} enabled backend(s). {disabled_count} disabled backend(s) hidden.[/dim]")
            console.print("[dim]   To see all backends: [bold]pipelex show backends --all[/bold][/dim]\n")

    console.print("[dim]💡 To enable more backends, edit: [bold].pipelex/inference/backends.toml[/bold][/dim]")
    console.print("[dim]💡 To list available models for a backend: [bold]pipelex show models <backend_name>[/bold][/dim]\n")
    get_telemetry_manager().track_event(EventName.BACKENDS_SHOW, properties={EventProperty.NB_BACKENDS: len(all_backends)})


# Typer group for show commands
show_app = typer.Typer(
    no_args_is_help=True,
)


@show_app.command("config", help="Display the main Pipelex configuration (not including inference backends)")
def show_config_cmd() -> None:
    do_show_config()


@show_app.command("pipes", help="List all available pipes in the current project")
def list_pipes_cmd() -> None:
    """List all pipes that have been loaded into the pipe library.

    This includes pipes from your project's .plx files and any
    pipes from imported packages.
    """
    try:
        Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_PIPES)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_PIPES)

    with get_telemetry_manager().telemetry_context():
        tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
        tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
        tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_PIPES}")

        do_list_pipes()


@show_app.command("pipe", help="Display the detailed definition of a specific pipe")
def show_pipe_cmd(
    pipe_code: Annotated[str, typer.Argument(help="Pipeline code to show definition for (e.g., 'my_domain.my_pipe')")],
) -> None:
    """Show the complete definition of a pipe including its inputs, outputs,
    prompt, and all configuration settings.

    Example:
        pipelex show pipe hello_world
    """
    try:
        Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_PIPE)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_PIPE)

    with get_telemetry_manager().telemetry_context():
        tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
        tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
        tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_PIPE}")

        do_show_pipe(pipe_code=pipe_code)


@show_app.command("models", help="List available AI models from a specific backend provider")
def show_models_cmd(
    backend_name: Annotated[str, typer.Argument(help="Backend name to list models for (e.g., 'openai', 'anthropic', 'google')")],
    flat: Annotated[
        bool,
        typer.Option("--flat", "-f", help="Output in flat CSV format for easy copy-pasting into configuration files"),
    ] = False,
) -> None:
    """List all available models from a configured backend provider.

    This queries the backend's API to retrieve the current list of available models.
    Use --flat for a simplified output that's easy to copy into config files.

    Examples:
        pipelex show models openai
        pipelex show models anthropic --flat
    """
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_MODELS)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_MODELS)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_MODELS}")

            asyncio.run(
                ModelLister.list_models(
                    backend_name=backend_name,
                    flat=flat,
                )
            )
    finally:
        pipelex_instance.teardown()


@show_app.command("backends", help="Display backend configurations and active routing profile")
def show_backends_cmd(
    show_all_backends: Annotated[bool, typer.Option("--all", "-a", help="Show all backends including disabled ones")] = False,
) -> None:
    """Display all configured backends and the active routing profile with its routing rules.

    By default, shows only enabled backends. Use --all to include disabled backends.

    Examples:
        pipelex show backends
        pipelex show backends --all
    """
    try:
        Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_BACKENDS)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_SHOW_BACKENDS)

    with get_telemetry_manager().telemetry_context():
        tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
        tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
        tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_BACKENDS}")

        do_show_backends(show_all=show_all_backends)
