import asyncio
import os
import shutil
from typing import Annotated, Optional

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_pipe_provider, get_pipeline_tracker, get_required_pipe
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipe_works.pipe_dry import dry_run_all_pipes, dry_run_single_pipe
from pipelex.pipelex import Pipelex
from pipelex.tools.config.manager import config_manager


def is_pipelex_libraries_folder(folder_path: str) -> bool:
    """Check if the given folder path contains a valid pipelex libraries structure.

    A valid pipelex libraries folder should contain the following subdirectories:
    - pipelines
    - llm_deck
    - llm_integrations
    - plugins
    - templates

    Args:
        folder_path: Path to the folder to check

    Returns:
        True if the folder contains all required subdirectories, False otherwise
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return False

    required_subdirs = [
        "pipelines",
        "llm_deck",
        "llm_integrations",
        "plugins",
        "templates",
    ]

    for subdir in required_subdirs:
        subdir_path = os.path.join(folder_path, subdir)
        if not os.path.exists(subdir_path) or not os.path.isdir(subdir_path):
            return False

    return True


class PipelexCLI(TyperGroup):
    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


@app.command("init-libraries")
def init_libraries(
    directory: Annotated[
        str,
        typer.Argument(help="Directory where to create the pipelex_libraries folder"),
    ] = ".",
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            "-o",
            help="Warning: If set, existing files will be overwritten.",
        ),
    ] = False,
) -> None:
    """Initialize pipelex libraries in a pipelex_libraries folder in the specified directory.

    If overwrite is False, only create files that don't exist yet.
    If overwrite is True, all files will be overwritten even if they exist.
    """
    try:
        # Always create a pipelex_libraries folder in the specified directory
        target_path = os.path.join(directory, "pipelex_libraries")

        # Create the target directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)

        # Create a LibraryConfig instance with the target path
        library_config = LibraryConfig(config_folder_path=target_path)
        library_config.export_libraries(overwrite=overwrite)

        if overwrite:
            typer.echo(f"✅ Successfully initialized pipelex libraries at '{target_path}' (all files overwritten)")
        else:
            typer.echo(f"✅ Successfully initialized pipelex libraries at '{target_path}' (only created non-existing files)")
    except Exception as exc:
        raise PipelexCLIError(f"Failed to initialize libraries at '{directory}': {exc}")


@app.command("init-config")
def init_config(
    reset: Annotated[
        bool,
        typer.Option("--reset", "-r", help="Warning: If set, existing files will be overwritten."),
    ] = False,
) -> None:
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
        raise PipelexCLIError(f"Failed to create pipelex.toml: {exc}")


@app.command()
def validate(
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "./pipelex_libraries",
) -> None:
    """Run the setup sequence."""
    # Check if pipelex libraries folder exists
    if not is_pipelex_libraries_folder(relative_config_folder_path):
        typer.echo(f"❌ No pipelex libraries folder found at '{relative_config_folder_path}'")
        typer.echo("To create a pipelex libraries folder, run: pipelex init-libraries")
        raise typer.Exit(1)

    pipelex_instance = Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_all_pipes())
    log.info("Setup sequence passed OK, config and pipelines are validated.")


@app.command()
def dry_run_pipe(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to dry run")],
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "./pipelex_libraries",
) -> None:
    """Dry run a single pipe."""
    # Check if pipelex libraries folder exists
    if not is_pipelex_libraries_folder(relative_config_folder_path):
        typer.echo(f"❌ No pipelex libraries folder found at '{relative_config_folder_path}'")
        typer.echo("To create a pipelex libraries folder, run: pipelex init-libraries")
        raise typer.Exit(1)

    try:
        # Initialize Pipelex
        pipelex_instance = Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
        pipelex_instance.validate_libraries()

        # Run the single pipe dry run
        asyncio.run(dry_run_single_pipe(pipe_code))
        get_pipeline_tracker().output_flowchart()

    except Exception as exc:
        typer.echo(f"❌ Error running dry run for pipe '{pipe_code}': {exc}")
        raise typer.Exit(1)


@app.command()
def show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(
            final_config,
            title=f"Pipelex configuration for project: {config_manager.get_project_name()}",
        )
    except Exception as exc:
        raise PipelexConfigError(f"Error loading configuration: {exc}")


@app.command()
def list_pipes(
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "pipelex_libraries",
) -> None:
    """List all available pipes."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    try:
        get_pipe_provider().pretty_list_pipes()

    except Exception as exc:
        raise PipelexCLIError(f"Failed to list pipes: {exc}")


@app.command("show-pipe")
def show_pipe(
    pipe_code: Annotated[
        str,
        typer.Argument(help="Pipeline code to show definition for"),
    ],
    relative_config_folder_path: Annotated[
        str,
        typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path"),
    ] = "./pipelex_libraries",
) -> None:
    """Show pipe from the pipe library."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipe = get_required_pipe(pipe_code=pipe_code)
    pretty_print(pipe, title=f"Pipe '{pipe_code}'")


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()
