from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.packages.exceptions import GraphBuildError, IndexBuildError
from pipelex.core.packages.graph.graph_builder import build_know_how_graph
from pipelex.core.packages.graph.models import NATIVE_PACKAGE_ADDRESS, ConceptId, PipeNode
from pipelex.core.packages.graph.query_engine import KnowHowQueryEngine
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


def _resolve_concept_fuzzy(concept_str: str, index: PackageIndex) -> list[tuple[ConceptId, str]]:
    """Fuzzy-resolve a concept string to matching ConceptIds.

    Collects candidates from native concepts and indexed concepts, matches
    case-insensitively against concept_code and concept_ref. Exact matches
    take priority to prevent 'Text' from ambiguously matching 'TextAndImages'.

    Args:
        concept_str: The user-provided concept string (e.g. "Text", "WeightedScore")
        index: The package index to search

    Returns:
        List of (ConceptId, concept_code) tuples for matching concepts
    """
    candidates: list[tuple[ConceptId, str]] = []
    lower_str = concept_str.lower()

    # Native concepts
    for native_code in NativeConceptCode:
        concept_ref = f"native.{native_code}"
        concept_id = ConceptId(
            package_address=NATIVE_PACKAGE_ADDRESS,
            concept_ref=concept_ref,
        )
        code_str: str = native_code.value
        if lower_str in code_str.lower() or lower_str in concept_ref.lower():
            candidates.append((concept_id, code_str))

    # Indexed concepts
    for address, concept in index.all_concepts():
        concept_id = ConceptId(
            package_address=address,
            concept_ref=concept.concept_ref,
        )
        if lower_str in concept.concept_code.lower() or lower_str in concept.concept_ref.lower():
            candidates.append((concept_id, concept.concept_code))

    # Exact-match priority: if any candidate's code or ref matches exactly, return only those
    exact_matches: list[tuple[ConceptId, str]] = []
    for cid, code in candidates:
        if code.lower() == lower_str or cid.concept_ref.lower() == lower_str:
            exact_matches.append((cid, code))

    if exact_matches:
        return exact_matches

    return candidates


def _display_ambiguous_concepts(
    matches: list[tuple[ConceptId, str]],
    concept_str: str,
    console: Console,
) -> None:
    """Display a table of ambiguous concept matches and a hint to refine the query."""
    console.print(f"[yellow]Ambiguous concept '{concept_str}' — matches {len(matches)} concepts:[/yellow]")
    table = Table(box=box.ROUNDED, show_header=True)
    table.add_column("Package", style="cyan")
    table.add_column("Concept Code")
    table.add_column("Concept Ref")
    for cid, code in matches:
        table.add_row(cid.package_address, code, cid.concept_ref)
    console.print(table)
    console.print("[dim]Refine your query to match exactly one concept.[/dim]")


def _display_type_search_pipes(pipes: list[PipeNode], title: str, console: Console) -> None:
    """Display a Rich table of pipe nodes matching type search results."""
    pipe_table = Table(title=title, box=box.ROUNDED, show_header=True)
    pipe_table.add_column("Package", style="cyan")
    pipe_table.add_column("Pipe")
    pipe_table.add_column("Type")
    pipe_table.add_column("Domain")
    pipe_table.add_column("Description")
    pipe_table.add_column("Exported")

    for pipe_node in pipes:
        exported_str = "[green]yes[/green]" if pipe_node.is_exported else "[dim]no[/dim]"
        pipe_table.add_row(
            pipe_node.package_address,
            pipe_node.pipe_code,
            pipe_node.pipe_type,
            pipe_node.domain_code,
            pipe_node.description,
            exported_str,
        )

    console.print(pipe_table)


def _handle_accepts_search(
    concept_str: str,
    index: PackageIndex,
    engine: KnowHowQueryEngine,
    console: Console,
    domain_filter: str | None = None,
) -> None:
    """Resolve concept fuzzy and find pipes that accept it."""
    matches = _resolve_concept_fuzzy(concept_str, index)
    if not matches:
        console.print(f"[yellow]No concept matching '{concept_str}' found.[/yellow]")
        return
    if len(matches) > 1:
        _display_ambiguous_concepts(matches, concept_str, console)
        raise typer.Exit(code=1)

    concept_id, concept_code = matches[0]
    pipes = engine.query_what_can_i_do(concept_id)
    if domain_filter is not None:
        pipes = [pipe_node for pipe_node in pipes if pipe_node.domain_code == domain_filter]
    if not pipes:
        console.print(f"[yellow]No pipes accept concept '{concept_code}' ({concept_id.concept_ref}).[/yellow]")
        return
    _display_type_search_pipes(pipes, f"Pipes that accept '{concept_code}'", console)


def _handle_produces_search(
    concept_str: str,
    index: PackageIndex,
    engine: KnowHowQueryEngine,
    console: Console,
    domain_filter: str | None = None,
) -> None:
    """Resolve concept fuzzy and find pipes that produce it."""
    matches = _resolve_concept_fuzzy(concept_str, index)
    if not matches:
        console.print(f"[yellow]No concept matching '{concept_str}' found.[/yellow]")
        return
    if len(matches) > 1:
        _display_ambiguous_concepts(matches, concept_str, console)
        raise typer.Exit(code=1)

    concept_id, concept_code = matches[0]
    pipes = engine.query_what_produces(concept_id)
    if domain_filter is not None:
        pipes = [pipe_node for pipe_node in pipes if pipe_node.domain_code == domain_filter]
    if not pipes:
        console.print(f"[yellow]No pipes produce concept '{concept_code}' ({concept_id.concept_ref}).[/yellow]")
        return
    _display_type_search_pipes(pipes, f"Pipes that produce '{concept_code}'", console)


def _do_type_search(
    index: PackageIndex,
    accepts: str | None,
    produces: str | None,
    console: Console,
    domain_filter: str | None = None,
) -> None:
    """Build the know-how graph and delegate to accepts/produces search handlers."""
    try:
        graph = build_know_how_graph(index)
    except GraphBuildError as exc:
        console.print(f"[red]Graph build error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    engine = KnowHowQueryEngine(graph)

    if accepts is not None:
        _handle_accepts_search(accepts, index, engine, console, domain_filter=domain_filter)
    if produces is not None:
        _handle_produces_search(produces, index, engine, console, domain_filter=domain_filter)


def do_pkg_search(
    query: str | None = None,
    domain: str | None = None,
    concept_only: bool = False,
    pipe_only: bool = False,
    cache: bool = False,
    accepts: str | None = None,
    produces: str | None = None,
) -> None:
    """Search the package index for concepts and pipes matching a query.

    Args:
        query: Search term (case-insensitive substring match).
        domain: Optional domain filter.
        concept_only: Show only matching concepts.
        pipe_only: Show only matching pipes.
        cache: Search cached packages instead of the current project.
        accepts: Find pipes that accept this concept (type-compatible search).
        produces: Find pipes that produce this concept (type-compatible search).
    """
    console = get_console()

    if query is None and accepts is None and produces is None:
        console.print("[red]Provide a search query or use --accepts/--produces for type search.[/red]")
        raise typer.Exit(code=1)

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

    if accepts is not None or produces is not None:
        _do_type_search(index, accepts, produces, console, domain_filter=domain)
        return

    assert query is not None

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
