from typing import Annotated

import typer

from pipelex.cli.commands.pkg.init_cmd import do_pkg_init
from pipelex.cli.commands.pkg.list_cmd import do_pkg_list

pkg_app = typer.Typer(
    no_args_is_help=True,
)


@pkg_app.command("init", help="Initialize a METHODS.toml package manifest from .mthds files in the current directory")
def pkg_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing METHODS.toml"),
    ] = False,
) -> None:
    """Scan .mthds files and generate a skeleton METHODS.toml."""
    do_pkg_init(force=force)


@pkg_app.command("list", help="Display the package manifest (METHODS.toml) for the current directory")
def pkg_list_cmd() -> None:
    """Show the package manifest if one exists."""
    do_pkg_list()
