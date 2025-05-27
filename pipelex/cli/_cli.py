import os
import shutil
from typing import Annotated, Optional

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipelex import Pipelex
from pipelex.tools.config.manager import config_manager


class PipelexCLI(TyperGroup):
    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


@app.command()
def init(
    overwrite: Annotated[bool, typer.Option("--overwrite", "-o", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    """Initialize pipelex configuration in the current directory."""
    if overwrite:
        typer.echo("Overwriting existing pipelex library files.")

    # Get the path to the default pipelex.toml in the package
    package_config_path = os.path.join(config_manager.pipelex_root_dir, "pipelex_init.toml")
    target_config_path = os.path.join(config_manager.local_root_dir, "pipelex.toml")

    # Check if target file exists and handle overwrite
    if os.path.exists(target_config_path) and not overwrite:
        typer.echo("Error: pipelex.toml already exists. Use --overwrite to force creation.", err=True)
        raise typer.Exit(1)

    # Copy the default config file
    try:
        shutil.copy2(package_config_path, target_config_path)
        typer.echo(f"Created pipelex.toml at {target_config_path}")
    except Exception as e:
        typer.echo(f"Error creating pipelex.toml: {e}", err=True)
        raise typer.Exit(1)

    # Duplicate pipelines and other libraries
    LibraryConfig.export_libraries(overwrite=overwrite)


@app.command()
def run_setup() -> None:
    """Run the setup sequence."""
    LibraryConfig.export_libraries()
    Pipelex.make()
    log.info("Running setup sequence passed OK.")


@app.command()
def show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(final_config, title=f"Pipelex configuration for project: {config_manager.get_project_name()}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()
