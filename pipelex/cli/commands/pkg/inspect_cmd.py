from pathlib import Path

import typer
from rich import box
from rich.table import Table

from pipelex.core.packages.exceptions import IndexBuildError
from pipelex.core.packages.index.index_builder import build_index_from_cache, build_index_from_project
from pipelex.hub import get_console


def do_pkg_inspect(address: str, cache: bool = False) -> None:
    """Display detailed information about a single package.

    Args:
        address: Package address to inspect.
        cache: Look in cache instead of the current project.
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
        console.print("[yellow]No packages found.[/yellow]")
        raise typer.Exit(code=1)

    entry = index.get_entry(address)
    if entry is None:
        available = ", ".join(sorted(index.entries.keys()))
        console.print(f"[red]Package '{address}' not found.[/red]")
        console.print(f"[dim]Available packages: {available}[/dim]")
        raise typer.Exit(code=1)

    # Package info table
    info_table = Table(title="Package Info", box=box.ROUNDED, show_header=True)
    info_table.add_column("Field", style="cyan")
    info_table.add_column("Value")
    info_table.add_row("Address", entry.address)
    if entry.display_name:
        info_table.add_row("Display Name", entry.display_name)
    info_table.add_row("Version", entry.version)
    info_table.add_row("Description", entry.description)
    if entry.authors:
        info_table.add_row("Authors", ", ".join(entry.authors))
    if entry.license:
        info_table.add_row("License", entry.license)
    if entry.dependencies:
        info_table.add_row("Dependencies", ", ".join(entry.dependencies))
    console.print(info_table)

    # Domains table
    if entry.domains:
        console.print()
        domain_table = Table(title="Domains", box=box.ROUNDED, show_header=True)
        domain_table.add_column("Domain Code", style="cyan")
        domain_table.add_column("Description")
        for domain in entry.domains:
            domain_table.add_row(domain.domain_code, domain.description or "[dim]-[/dim]")
        console.print(domain_table)

    # Concepts table
    if entry.concepts:
        console.print()
        concept_table = Table(title="Concepts", box=box.ROUNDED, show_header=True)
        concept_table.add_column("Concept", style="cyan")
        concept_table.add_column("Domain")
        concept_table.add_column("Description")
        concept_table.add_column("Refines")
        concept_table.add_column("Fields")
        for concept in entry.concepts:
            fields_str = ", ".join(concept.structure_fields) if concept.structure_fields else "[dim]-[/dim]"
            concept_table.add_row(
                concept.concept_code,
                concept.domain_code,
                concept.description,
                concept.refines or "[dim]-[/dim]",
                fields_str,
            )
        console.print(concept_table)

    # Pipes table
    if entry.pipes:
        console.print()
        pipe_table = Table(title="Pipe Signatures", box=box.ROUNDED, show_header=True)
        pipe_table.add_column("Pipe", style="cyan")
        pipe_table.add_column("Type")
        pipe_table.add_column("Domain")
        pipe_table.add_column("Description")
        pipe_table.add_column("Inputs")
        pipe_table.add_column("Output")
        pipe_table.add_column("Exported")
        for pipe in entry.pipes:
            inputs_str = ", ".join(f"{key}: {val}" for key, val in pipe.input_specs.items()) if pipe.input_specs else "[dim]-[/dim]"
            exported_str = "[green]yes[/green]" if pipe.is_exported else "[dim]no[/dim]"
            pipe_table.add_row(
                pipe.pipe_code,
                pipe.pipe_type,
                pipe.domain_code,
                pipe.description,
                inputs_str,
                pipe.output_spec,
                exported_str,
            )
        console.print(pipe_table)

    console.print()
