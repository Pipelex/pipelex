from typing import Annotated

import typer

from pipelex.cli.commands.pkg.add_cmd import do_pkg_add
from pipelex.cli.commands.pkg.graph_cmd import do_pkg_graph
from pipelex.cli.commands.pkg.index_cmd import do_pkg_index
from pipelex.cli.commands.pkg.init_cmd import do_pkg_init
from pipelex.cli.commands.pkg.inspect_cmd import do_pkg_inspect
from pipelex.cli.commands.pkg.install_cmd import do_pkg_install
from pipelex.cli.commands.pkg.list_cmd import do_pkg_list
from pipelex.cli.commands.pkg.lock_cmd import do_pkg_lock
from pipelex.cli.commands.pkg.publish_cmd import do_pkg_publish
from pipelex.cli.commands.pkg.search_cmd import do_pkg_search
from pipelex.cli.commands.pkg.update_cmd import do_pkg_update

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


@pkg_app.command("lock", help="Resolve dependencies and generate methods.lock")
def pkg_lock_cmd() -> None:
    """Resolve all dependencies and write a lock file."""
    do_pkg_lock()


@pkg_app.command("install", help="Install dependencies from methods.lock")
def pkg_install_cmd() -> None:
    """Fetch packages recorded in the lock file."""
    do_pkg_install()


@pkg_app.command("update", help="Re-resolve dependencies and update methods.lock")
def pkg_update_cmd() -> None:
    """Fresh resolve of all dependencies and rewrite the lock file."""
    do_pkg_update()


@pkg_app.command("index", help="Build and display the package index")
def pkg_index_cmd(
    cache: Annotated[
        bool,
        typer.Option("--cache", "-c", help="Index cached packages instead of current project"),
    ] = False,
) -> None:
    """Build and display the package index."""
    do_pkg_index(cache=cache)


@pkg_app.command("search", help="Search the package index for concepts and pipes")
def pkg_search_cmd(
    query: Annotated[
        str,
        typer.Argument(help="Search term (case-insensitive substring match)"),
    ],
    domain: Annotated[
        str | None,
        typer.Option("--domain", "-d", help="Filter to specific domain"),
    ] = None,
    concept: Annotated[
        bool,
        typer.Option("--concept", help="Show only matching concepts"),
    ] = False,
    pipe: Annotated[
        bool,
        typer.Option("--pipe", help="Show only matching pipes"),
    ] = False,
    cache: Annotated[
        bool,
        typer.Option("--cache", "-c", help="Search cached packages"),
    ] = False,
) -> None:
    """Search the package index for concepts and pipes matching a query."""
    do_pkg_search(query=query, domain=domain, concept_only=concept, pipe_only=pipe, cache=cache)


@pkg_app.command("inspect", help="Display detailed information about a package")
def pkg_inspect_cmd(
    address: Annotated[
        str,
        typer.Argument(help="Package address to inspect"),
    ],
    cache: Annotated[
        bool,
        typer.Option("--cache", "-c", help="Look in cache"),
    ] = False,
) -> None:
    """Display detailed information about a single package."""
    do_pkg_inspect(address=address, cache=cache)


@pkg_app.command("graph", help="Query the know-how graph for concept/pipe relationships")
def pkg_graph_cmd(
    from_concept: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Concept ID (package::concept_ref) — find pipes that accept it"),
    ] = None,
    to_concept: Annotated[
        str | None,
        typer.Option("--to", "-t", help="Concept ID — find pipes that produce it"),
    ] = None,
    check: Annotated[
        str | None,
        typer.Option("--check", help="Two pipe keys comma-separated — check compatibility"),
    ] = None,
    max_depth: Annotated[
        int,
        typer.Option("--max-depth", "-m", help="Max chain depth for --from + --to together"),
    ] = 3,
    cache: Annotated[
        bool,
        typer.Option("--cache", "-c", help="Use cached packages"),
    ] = False,
) -> None:
    """Query the know-how graph for concept/pipe relationships."""
    do_pkg_graph(from_concept=from_concept, to_concept=to_concept, check=check, max_depth=max_depth, cache=cache)


@pkg_app.command("publish", help="Validate package readiness for distribution")
def pkg_publish_cmd(
    tag: Annotated[
        bool,
        typer.Option("--tag", help="Create git tag v{version} locally on success"),
    ] = False,
) -> None:
    """Validate that the package is ready for distribution."""
    do_pkg_publish(tag=tag)
