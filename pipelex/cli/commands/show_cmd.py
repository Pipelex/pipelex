from __future__ import annotations

from typing import Annotated

import typer

from pipelex import pretty_print
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_pipe_provider, get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.tools.config.manager import config_manager


def do_show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(
            final_config,
            title=f"Pipelex configuration for project: {config_manager.get_project_name()}",
        )
    except Exception as exc:
        raise PipelexConfigError(f"Error loading configuration: {exc}") from exc


def do_list_pipes(relative_config_folder_path: str = "pipelex_libraries") -> None:
    """List all available pipes."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    try:
        get_pipe_provider().pretty_list_pipes()
    except Exception as exc:
        raise PipelexCLIError(f"Failed to list pipes: {exc}") from exc


def do_show_pipe(pipe_code: str, relative_config_folder_path: str = "./pipelex_libraries") -> None:
    """Show a single pipe definition from the library."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipe = get_required_pipe(pipe_code=pipe_code)
    pretty_print(pipe, title=f"Pipe '{pipe_code}'")


# Typer group for show commands
show_app = typer.Typer(help="Show and list commands", no_args_is_help=True)


@show_app.command("config")
def show_config_cmd() -> None:
    do_show_config()


@show_app.command("pipes")
def list_pipes_cmd(
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "pipelex_libraries",
) -> None:
    do_list_pipes(relative_config_folder_path=relative_config_folder_path)


@show_app.command("pipe")
def show_pipe_cmd(
    pipe_code: Annotated[str, typer.Argument(help="Pipeline code to show definition for")],
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "./pipelex_libraries",
) -> None:
    do_show_pipe(pipe_code=pipe_code, relative_config_folder_path=relative_config_folder_path)
