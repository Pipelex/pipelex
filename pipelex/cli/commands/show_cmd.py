from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from pipelex import pretty_print
from pipelex.cogt.model_backends.model_lists import ModelLister
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_pipe_library, get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.config_loader import config_manager


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
    Pipelex.make()

    try:
        get_pipe_library().pretty_list_pipes()
    except Exception as exc:
        msg = f"Failed to list pipes: {exc}"
        raise PipelexCLIError(msg) from exc


def do_show_pipe(pipe_code: str) -> None:
    """Show a single pipe definition from the library."""
    Pipelex.make()
    pipe = get_required_pipe(pipe_code=pipe_code)
    pretty_print(pipe, title=f"Pipe '{pipe_code}'")


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
    asyncio.run(
        ModelLister.list_models(
            backend_name=backend_name,
            flat=flat,
        )
    )
