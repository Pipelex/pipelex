from pathlib import Path

import typer
from rich import box
from rich.table import Table

from pipelex.core.packages.exceptions import IndexBuildError
from pipelex.core.packages.index.index_builder import build_index_from_cache, build_index_from_project
from pipelex.hub import get_console


def do_pkg_index(cache: bool = False) -> None:
    """Build and display the package index.

    Args:
        cache: If True, index cached packages instead of the current project.
    """
    console = get_console()

    try:
        if cache:
            index = build_index_from_cache()
        else:
            index = build_index_from_project(Path.cwd())
    except IndexBuildError as exc:
        console.print(f"[red]Index build error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not index.entries:
        console.print("[yellow]No packages found to index.[/yellow]")
        raise typer.Exit(code=1)

    has_display_name = any(entry.display_name for entry in index.entries.values())

    table = Table(title="Package Index", box=box.ROUNDED, show_header=True)
    table.add_column("Address", style="cyan")
    if has_display_name:
        table.add_column("Display Name")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Domains", justify="right")
    table.add_column("Concepts", justify="right")
    table.add_column("Pipes", justify="right")

    for entry in index.entries.values():
        row: list[str] = [entry.address]
        if has_display_name:
            row.append(entry.display_name or "")
        row.extend(
            [
                entry.version,
                entry.description,
                str(len(entry.domains)),
                str(len(entry.concepts)),
                str(len(entry.pipes)),
            ]
        )
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]{len(index.entries)} package(s) indexed.[/dim]")
