# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

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

    # Duplicate pipelines and other libraries from the base library
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
