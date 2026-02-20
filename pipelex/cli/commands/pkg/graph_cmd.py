from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from pipelex.core.packages.exceptions import GraphBuildError, IndexBuildError
from pipelex.core.packages.graph.chain_formatter import format_chain_as_mthds_snippet
from pipelex.core.packages.graph.graph_builder import build_know_how_graph
from pipelex.core.packages.graph.models import ConceptId, KnowHowGraph, PipeNode
from pipelex.core.packages.graph.query_engine import KnowHowQueryEngine
from pipelex.core.packages.index.index_builder import build_index_from_cache, build_index_from_project
from pipelex.hub import get_console


def _parse_concept_id(raw: str) -> ConceptId:
    """Parse a concept ID string in the format 'package_address::concept_ref'.

    Args:
        raw: String like '__native__::native.Text' or 'github.com/org/repo::domain.Concept'

    Returns:
        A ConceptId instance.

    Raises:
        typer.Exit: If the format is invalid.
    """
    console = get_console()

    if "::" not in raw:
        console.print(f"[red]Invalid concept format: '{escape(raw)}'[/red]")
        console.print("[dim]Expected format: package_address::concept_ref (e.g. __native__::native.Text)[/dim]")
        raise typer.Exit(code=1)

    if raw.count("::") > 1:
        console.print(f"[red]Invalid concept format: '{escape(raw)}' contains multiple '::' separators.[/red]")
        console.print("[dim]Expected format: package_address::concept_ref (e.g. __native__::native.Text)[/dim]")
        raise typer.Exit(code=1)

    separator_index = raw.index("::")
    package_address = raw[:separator_index]
    concept_ref = raw[separator_index + 2 :]

    if not package_address or not concept_ref:
        console.print(f"[red]Invalid concept format: '{escape(raw)}' — both package_address and concept_ref must be non-empty.[/red]")
        console.print("[dim]Expected format: package_address::concept_ref (e.g. __native__::native.Text)[/dim]")
        raise typer.Exit(code=1)

    return ConceptId(package_address=package_address, concept_ref=concept_ref)


def do_pkg_graph(
    from_concept: str | None = None,
    to_concept: str | None = None,
    check: str | None = None,
    max_depth: int = 3,
    cache: bool = False,
    compose: bool = False,
) -> None:
    """Query the know-how graph for concept/pipe relationships.

    Args:
        from_concept: Concept ID to find pipes that accept it.
        to_concept: Concept ID to find pipes that produce it.
        check: Two pipe keys comma-separated to check compatibility.
        max_depth: Max chain depth for --from + --to together.
        cache: Use cached packages instead of the current project.
        compose: Show MTHDS composition template (requires --from and --to).
    """
    console = get_console()

    if compose and (not from_concept or not to_concept):
        console.print("[red]--compose requires both --from and --to.[/red]")
        raise typer.Exit(code=1)

    if not from_concept and not to_concept and not check:
        console.print("[red]Please specify at least one of --from, --to, or --check.[/red]")
        console.print("[dim]Run 'pipelex pkg graph --help' for usage.[/dim]")
        raise typer.Exit(code=1)

    try:
        if cache:
            index = build_index_from_cache()
        else:
            index = build_index_from_project(Path.cwd())
    except IndexBuildError as exc:
        console.print(f"[red]Index build error: {escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from exc

    if not index.entries:
        console.print("[yellow]No packages found.[/yellow]")
        raise typer.Exit(code=1)

    try:
        graph = build_know_how_graph(index)
    except GraphBuildError as exc:
        console.print(f"[red]Graph build error: {escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from exc

    engine = KnowHowQueryEngine(graph)

    if check:
        _handle_check(console, engine, check)
    elif from_concept and to_concept:
        _handle_from_to(console, engine, graph, from_concept, to_concept, max_depth, compose)
    elif from_concept:
        _handle_from(console, engine, from_concept)
    elif to_concept:
        _handle_to(console, engine, to_concept)


def _handle_from(console: Console, engine: KnowHowQueryEngine, raw_concept: str) -> None:
    """Find pipes that accept the given concept."""
    concept_id = _parse_concept_id(raw_concept)
    pipes = engine.query_what_can_i_do(concept_id)

    if not pipes:
        console.print(f"[yellow]No pipes accept concept '{escape(raw_concept)}'.[/yellow]")
        return

    table = Table(title=f"Pipes accepting {raw_concept}", box=box.ROUNDED, show_header=True)
    table.add_column("Package", style="cyan")
    table.add_column("Pipe")
    table.add_column("Type")
    table.add_column("Output")
    table.add_column("Exported")

    for pipe_node in pipes:
        exported_str = "[green]yes[/green]" if pipe_node.is_exported else "[dim]no[/dim]"
        table.add_row(
            pipe_node.package_address,
            pipe_node.pipe_code,
            pipe_node.pipe_type,
            pipe_node.output_concept_id.concept_ref,
            exported_str,
        )

    console.print(table)


def _handle_to(console: Console, engine: KnowHowQueryEngine, raw_concept: str) -> None:
    """Find pipes that produce the given concept."""
    concept_id = _parse_concept_id(raw_concept)
    pipes = engine.query_what_produces(concept_id)

    if not pipes:
        console.print(f"[yellow]No pipes produce concept '{escape(raw_concept)}'.[/yellow]")
        return

    table = Table(title=f"Pipes producing {raw_concept}", box=box.ROUNDED, show_header=True)
    table.add_column("Package", style="cyan")
    table.add_column("Pipe")
    table.add_column("Type")
    table.add_column("Inputs")
    table.add_column("Exported")

    for pipe_node in pipes:
        inputs_str = ", ".join(f"{key}: {val.concept_ref}" for key, val in pipe_node.input_concept_ids.items())
        exported_str = "[green]yes[/green]" if pipe_node.is_exported else "[dim]no[/dim]"
        table.add_row(
            pipe_node.package_address,
            pipe_node.pipe_code,
            pipe_node.pipe_type,
            inputs_str or "[dim]-[/dim]",
            exported_str,
        )

    console.print(table)


def _handle_from_to(
    console: Console,
    engine: KnowHowQueryEngine,
    graph: KnowHowGraph,
    raw_from: str,
    raw_to: str,
    max_depth: int,
    compose: bool,
) -> None:
    """Find pipe chains from input concept to output concept."""
    from_id = _parse_concept_id(raw_from)
    to_id = _parse_concept_id(raw_to)
    chains = engine.query_i_have_i_need(from_id, to_id, max_depth=max_depth)

    if not chains:
        console.print(f"[yellow]No pipe chains found from '{escape(raw_from)}' to '{escape(raw_to)}' (max depth {max_depth}).[/yellow]")
        return

    if compose:
        _print_compose_output(console, graph, chains, from_id, to_id)
    else:
        console.print(f"[bold]Pipe chains from {escape(raw_from)} to {escape(raw_to)}:[/bold]\n")
        for chain_index, chain in enumerate(chains, start=1):
            steps = " -> ".join(chain)
            console.print(f"  {chain_index}. {steps}")
        console.print(f"\n[dim]{len(chains)} chain(s) found.[/dim]")


def _print_compose_output(
    console: Console,
    graph: KnowHowGraph,
    chains: list[list[str]],
    from_id: ConceptId,
    to_id: ConceptId,
) -> None:
    """Print MTHDS composition templates for discovered chains."""
    multiple = len(chains) > 1

    for chain_index, chain in enumerate(chains, start=1):
        pipe_nodes: list[PipeNode] = []
        for node_key in chain:
            pipe_node = graph.get_pipe_node(node_key)
            if pipe_node is not None:
                pipe_nodes.append(pipe_node)

        snippet = format_chain_as_mthds_snippet(pipe_nodes, from_id, to_id)
        if not snippet:
            continue

        if multiple:
            console.print(f"[bold]Chain {chain_index} of {len(chains)}:[/bold]")
        console.print(snippet)
        if multiple and chain_index < len(chains):
            console.print()


def _handle_check(console: Console, engine: KnowHowQueryEngine, check_arg: str) -> None:
    """Check compatibility between two pipes."""
    parts = check_arg.split(",")
    if len(parts) != 2:
        console.print("[red]--check requires exactly two pipe keys separated by a comma.[/red]")
        console.print("[dim]Example: --check 'pkg::pipe_a,pkg::pipe_b'[/dim]")
        raise typer.Exit(code=1)

    source_key = parts[0].strip()
    target_key = parts[1].strip()

    if not source_key or not target_key:
        console.print("[red]--check requires two non-empty pipe keys separated by a comma.[/red]")
        console.print("[dim]Example: --check 'pkg::pipe_a,pkg::pipe_b'[/dim]")
        raise typer.Exit(code=1)

    compatible_params = engine.check_compatibility(source_key, target_key)

    if compatible_params:
        console.print(
            f"[green]Compatible![/green] Output of '{escape(source_key)}' can feed into '{escape(target_key)}' via: {', '.join(compatible_params)}"
        )
    else:
        console.print(f"[yellow]Not compatible.[/yellow] Output of '{escape(source_key)}' does not match any input of '{escape(target_key)}'.")
