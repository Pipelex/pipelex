from typing import Annotated

import typer

from pipelex.cli.commands.pkg.add_cmd import do_pkg_add
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


@pkg_app.command("add", help="Add a dependency to METHODS.toml")
def pkg_add_cmd(
    address: Annotated[
        str,
        typer.Argument(help="Package address (e.g. 'github.com/org/repo')"),
    ],
    alias: Annotated[
        str | None,
        typer.Option("--alias", "-a", help="Dependency alias (auto-derived from address if not provided)"),
    ] = None,
    version: Annotated[
        str,
        typer.Option("--version", "-v", help="Version constraint"),
    ] = "0.1.0",
    path: Annotated[
        str | None,
        typer.Option("--path", "-p", help="Local filesystem path to the dependency"),
    ] = None,
) -> None:
    """Add a dependency to the package manifest."""
    do_pkg_add(address=address, alias=alias, version=version, path=path)
