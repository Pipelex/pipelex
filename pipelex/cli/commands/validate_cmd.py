from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from pipelex import log
from pipelex.cli.commands.common import is_pipelex_libraries_folder
from pipelex.hub import get_pipeline_tracker
from pipelex.pipe_works.pipe_dry import dry_run_all_pipes, dry_run_single_pipe
from pipelex.pipelex import Pipelex


def do_validate_all_libraries_and_dry_run(relative_config_folder_path: str = "./pipelex_libraries") -> None:
    """Validate libraries and dry-run all pipes."""
    if not is_pipelex_libraries_folder(relative_config_folder_path):
        typer.echo(f"❌ No pipelex libraries folder found at '{relative_config_folder_path}'")
        typer.echo("To create a pipelex libraries folder, run: pipelex init-libraries")
        raise typer.Exit(1)

    pipelex_instance = Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_all_pipes())
    log.info("Setup sequence passed OK, config and pipelines are validated.")


def do_dry_run_pipe(pipe_code: str, relative_config_folder_path: str = "./pipelex_libraries") -> None:
    """Dry run a single pipe."""
    if not is_pipelex_libraries_folder(relative_config_folder_path):
        typer.echo(f"❌ No pipelex libraries folder found at '{relative_config_folder_path}'")
        typer.echo("To create a pipelex libraries folder, run: pipelex init-libraries")
        raise typer.Exit(1)

    pipelex_instance = Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_single_pipe(pipe_code))

    typer.echo(f"✅ Pipe '{pipe_code}' validation successful")
    get_pipeline_tracker().output_flowchart()


# Typer group for validation commands
validate_app = typer.Typer(help="Validation and dry-run commands", no_args_is_help=True)


@validate_app.command("all")
def validate_all_cmd(
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "./pipelex_libraries",
) -> None:
    do_validate_all_libraries_and_dry_run(relative_config_folder_path=relative_config_folder_path)


@validate_app.command("pipe")
def dry_run_pipe_cmd(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to dry run")],
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "./pipelex_libraries",
) -> None:
    do_dry_run_pipe(pipe_code=pipe_code, relative_config_folder_path=relative_config_folder_path)
