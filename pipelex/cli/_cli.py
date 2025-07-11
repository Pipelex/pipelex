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
from pipelex.hub import get_pipe_provider
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipe_works.pipe_dry import dry_run_all_pipes
from pipelex.pipelex import Pipelex
from pipelex.tools.config.manager import config_manager


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
    overwrite: Annotated[bool, typer.Option("--overwrite", "-o", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    """Initialize pipelex libraries in the current directory.

    If overwrite is False, only create files that don't exist yet.
    If overwrite is True, all files will be overwritten even if they exist.
    """
    try:
        # TODO: Have a more proper print message regarding the overwrited files (e.g. list of files that were overwritten or not)
        LibraryConfig().export_libraries(overwrite=overwrite)
        if overwrite:
            typer.echo("Successfully initialized pipelex libraries (all files overwritten)")
        else:
            typer.echo("Successfully initialized pipelex libraries (only created non-existing files)")
    except Exception as e:
        raise PipelexCLIError(f"Failed to initialize libraries: {e}")


@app.command("init-config")
def init_config(
    reset: Annotated[bool, typer.Option("--reset", "-r", help="Warning: If set, existing files will be overwritten.")] = False,
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
    except Exception as e:
        raise PipelexCLIError(f"Failed to create pipelex.toml: {e}")


@app.command()
def validate(
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "pipelex_libraries",
) -> None:
    """Run the setup sequence."""
    config_folder_path = os.path.join(os.getcwd(), relative_config_folder_path)
    LibraryConfig(config_folder_path=config_folder_path).export_libraries()
    pipelex_instance = Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_all_pipes())
    log.info("Setup sequence passed OK, config and pipelines are validated.")


@app.command()
def show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(final_config, title=f"Pipelex configuration for project: {config_manager.get_project_name()}")
    except Exception as e:
        raise PipelexConfigError(f"Error loading configuration: {e}")


@app.command()
def list_pipes(
    relative_config_folder_path: Annotated[
        str, typer.Option("--config-folder-path", "-c", help="Relative path to the config folder path")
    ] = "pipelex_libraries",
) -> None:
    """List all available pipes."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    try:
        get_pipe_provider().pretty_list_pipes()

    except Exception as e:
        raise PipelexCLIError(f"Failed to list pipes: {e}")


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()
