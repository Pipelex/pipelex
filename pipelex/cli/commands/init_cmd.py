from __future__ import annotations

import os
import shutil
from typing import Annotated

import typer

from pipelex.exceptions import PipelexCLIError
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.config.manager import config_manager


def do_init_libraries(directory: str = ".", overwrite: bool = False) -> None:
    """Initialize pipelex libraries in a pipelex_libraries folder in the specified directory."""
    try:
        target_dir = os.path.join(directory, "pipelex_libraries")
        os.makedirs(directory, exist_ok=True)

        library_config = LibraryConfig(config_dir_path=target_dir)
        library_config.export_libraries(overwrite=overwrite)

        if overwrite:
            typer.echo(f"✅ Successfully initialized pipelex libraries at '{target_dir}' (all files overwritten)")
        else:
            typer.echo(f"✅ Successfully initialized pipelex libraries at '{target_dir}' (only created non-existing files)")
    except Exception as exc:
        raise PipelexCLIError(f"Failed to initialize libraries at '{directory}': {exc}") from exc


def do_init_config(reset: bool = False) -> None:
    """Initialize pipelex configuration in the current directory."""
    pipelex_template_path = os.path.join(config_manager.pipelex_root_dir, "pipelex_template.toml")
    target_config_path = os.path.join(config_manager.local_root_dir, "pipelex.toml")

    if os.path.exists(target_config_path) and not reset:
        typer.echo("Warning: pipelex.toml already exists. Use --reset to force creation.")
        return

    try:
        shutil.copy2(pipelex_template_path, target_config_path)
        typer.echo(f"Created pipelex.toml at {target_config_path}")
    except Exception as exc:
        raise PipelexCLIError(f"Failed to create pipelex.toml: {exc}") from exc


# Typer group for init commands
init_app = typer.Typer(help="Initialization commands", no_args_is_help=True)


@init_app.command("libraries")
def init_libraries_cmd(
    directory: Annotated[str, typer.Argument(help="Directory where to create the pipelex_libraries folder")] = ".",
    overwrite: Annotated[bool, typer.Option("--overwrite", "-o", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    do_init_libraries(directory=directory, overwrite=overwrite)


@init_app.command("config")
def init_config_cmd(
    reset: Annotated[bool, typer.Option("--reset", "-r", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    do_init_config(reset=reset)
