from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from anthropic import AuthenticationError
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import pretty_print
from pipelex.cogt.exceptions import MissingDependencyError
from pipelex.cogt.model_backends.model_lists import do_show_models
from pipelex.config import get_config
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_models_manager, get_pipe_provider, get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicSDKUnsupportedError
from pipelex.plugins.anthropic.anthropic_llms import anthropic_list_available_models
from pipelex.plugins.mistral.mistral_llms import mistral_list_available_models
from pipelex.plugins.openai.openai_llms import openai_list_available_models
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.aws.aws_config import AwsCredentialsError
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
        msg = f"Error loading configuration: {exc}"
        raise PipelexConfigError(msg) from exc


def do_list_pipes(relative_config_folder_path: str = "pipelex_libraries") -> None:
    """List all available pipes."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    try:
        get_pipe_provider().pretty_list_pipes()
    except Exception as exc:
        msg = f"Failed to list pipes: {exc}"
        raise PipelexCLIError(msg) from exc


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
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "pipelex_libraries",
) -> None:
    do_list_pipes(relative_config_folder_path=relative_config_folder_path)


@show_app.command("pipe")
def show_pipe_cmd(
    pipe_code: Annotated[str, typer.Argument(help="Pipeline code to show definition for")],
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "./pipelex_libraries",
) -> None:
    do_show_pipe(pipe_code=pipe_code, relative_config_folder_path=relative_config_folder_path)


@show_app.command("models")
def show_models_cmd(
    backend_name: Annotated[str, typer.Argument(help="Backend name to list models for")],
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "./pipelex_libraries",
    flat: Annotated[
        bool,
        typer.Option("--flat", "-f", help="Output in flat CSV format for easy copy-pasting"),
    ] = False,
) -> None:
    asyncio.run(
        do_show_models(
            backend_name=backend_name,
            relative_config_folder_path=relative_config_folder_path,
            flat=flat,
        )
    )
