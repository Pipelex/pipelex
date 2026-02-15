from pathlib import Path

import typer
from rich import box
from rich.table import Table

from pipelex.core.packages.exceptions import IndexBuildError
from pipelex.core.packages.index.index_builder import build_index_from_cache, build_index_from_project
from pipelex.core.packages.index.models import ConceptEntry, PackageIndex, PipeSignature
from pipelex.hub import get_console


def _matches(query: str, *fields: str | None) -> bool:
    """Case-insensitive substring match against any of the provided fields."""
    lower_query = query.lower()
    return any(field is not None and lower_query in field.lower() for field in fields)


def _search_concepts(index: PackageIndex, query: str, domain_filter: str | None) -> list[tuple[str, ConceptEntry]]:
    """Find concepts matching the query, optionally filtered by domain."""
    results: list[tuple[str, ConceptEntry]] = []
    for address, concept in index.all_concepts():
        if domain_filter and concept.domain_code != domain_filter:
            continue
        if _matches(query, concept.concept_code, concept.description, concept.concept_ref):
            results.append((address, concept))
    return results


def _search_pipes(index: PackageIndex, query: str, domain_filter: str | None) -> list[tuple[str, PipeSignature]]:
    """Find pipes matching the query, optionally filtered by domain."""
    results: list[tuple[str, PipeSignature]] = []
    for address, pipe in index.all_pipes():
        if domain_filter and pipe.domain_code != domain_filter:
            continue
        if _matches(query, pipe.pipe_code, pipe.description, pipe.output_spec):
            results.append((address, pipe))
    return results


def do_pkg_search(
    query: str,
    domain: str | None = None,
    concept_only: bool = False,
    pipe_only: bool = False,
    cache: bool = False,
) -> None:
    """Search the package index for concepts and pipes matching a query.

    Args:
        query: Search term (case-insensitive substring match).
        domain: Optional domain filter.
        concept_only: Show only matching concepts.
        pipe_only: Show only matching pipes.
        cache: Search cached packages instead of the current project.
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
        console.print("[yellow]No packages found to search.[/yellow]")
        raise typer.Exit(code=1)

    both_or_neither = concept_only == pipe_only
    show_concepts = both_or_neither or concept_only
    show_pipes = both_or_neither or pipe_only

    matching_concepts = _search_concepts(index, query, domain) if show_concepts else []
    matching_pipes = _search_pipes(index, query, domain) if show_pipes else []

    if not matching_concepts and not matching_pipes:
        console.print(f"[yellow]No results matching '{query}'.[/yellow]")
        return

    if matching_concepts:
        concept_table = Table(title="Matching Concepts", box=box.ROUNDED, show_header=True)
        concept_table.add_column("Package", style="cyan")
        concept_table.add_column("Concept")
        concept_table.add_column("Domain")
        concept_table.add_column("Description")
        concept_table.add_column("Refines")

        for address, concept in matching_concepts:
            concept_table.add_row(
                address,
                concept.concept_code,
                concept.domain_code,
                concept.description,
                concept.refines or "[dim]-[/dim]",
            )

        console.print(concept_table)

    if matching_pipes:
        pipe_table = Table(title="Matching Pipes", box=box.ROUNDED, show_header=True)
        pipe_table.add_column("Package", style="cyan")
        pipe_table.add_column("Pipe")
        pipe_table.add_column("Type")
        pipe_table.add_column("Domain")
        pipe_table.add_column("Description")
        pipe_table.add_column("Exported")

        for address, pipe in matching_pipes:
            exported_str = "[green]yes[/green]" if pipe.is_exported else "[dim]no[/dim]"
            pipe_table.add_row(
                address,
                pipe.pipe_code,
                pipe.pipe_type,
                pipe.domain_code,
                pipe.description,
                exported_str,
            )

        console.print(pipe_table)
