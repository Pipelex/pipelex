from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.run._run_core import COMMAND, execute_run
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def run_pipe_cmd(
    pipe_code: Annotated[
        str,
        typer.Argument(help="Pipe code to run"),
    ],
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Path to JSON file with inputs"),
    ] = None,
    save_working_memory: Annotated[
        bool,
        typer.Option("--save-working-memory/--no-save-working-memory", help="Save working memory to JSON file"),
    ] = True,
    working_memory_path: Annotated[
        str | None,
        typer.Option("--working-memory-path", help="Custom path to save working memory JSON"),
    ] = None,
    save_main_stuff: Annotated[
        bool,
        typer.Option("--save-main-stuff/--no-save-main-stuff", help="Save main_stuff in JSON and Markdown formats"),
    ] = True,
    no_pretty_print: Annotated[
        bool,
        typer.Option("--no-pretty-print", help="Skip pretty printing the main_stuff"),
    ] = False,
    graph: Annotated[
        bool | None,
        typer.Option(
            "--graph/--no-graph",
            help="Override config: enable or disable execution graph outputs (JSON, Mermaid, HTML)",
        ),
    ] = None,
    graph_full_data: Annotated[
        bool | None,
        typer.Option(
            "--graph-full-data/--graph-no-data",
            help="Override config: include or exclude full serialized data in graph",
        ),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", "-o", help="Base directory for all outputs (working memory, main_stuff, graphs)"),
    ] = "results",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
    temporal: Annotated[
        bool | None,
        typer.Option("--temporal/--no-temporal", help="Override config: enable or disable Temporal workflow execution"),
    ] = None,
    dynamic_output_concept_ref: Annotated[
        str | None,
        typer.Option(
            "--dynamic-output-concept",
            "-O",
            help="Concept ref (e.g. 'document_qa.ReferenceCount') used to resolve a pipe whose output is declared as 'Dynamic'.",
        ),
    ] = None,
    cost_report: Annotated[
        bool | None,
        typer.Option(
            "--cost-report/--no-cost-report",
            help="Override config: --cost-report forces the cost table on; --no-cost-report skips reporting entirely (no table and no CSV file).",
        ),
    ] = None,
    save_csv: Annotated[
        str | None,
        typer.Option(
            "--save-csv",
            help="Write the main stuff to this CSV path (literal, cwd-relative; NOT under --output-dir). Requires a flat list output.",
        ),
    ] = None,
) -> None:
    """Run a pipe by code.

    Examples:
        pipelex run pipe my_pipe
        pipelex run pipe my_pipe --inputs data.json
        pipelex run pipe my_pipe --dry-run
        pipelex run pipe my_pipe --dry-run --mock-inputs
    """
    # Helpful error if the user passes a path instead of a pipe code
    target_path = Path(pipe_code)
    if target_path.is_dir() or is_pipelex_file(target_path) or pipe_code.endswith(MTHDS_EXTENSION):
        typer.secho(
            f"Failed to run: '{pipe_code}' looks like a file path or directory.\n"
            f"  To run from a bundle or directory, use: pipelex run bundle {pipe_code}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        typer.secho(
            "Failed to run: --mock-inputs requires --dry-run",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Check installed methods' exports for additional library dirs
    try:
        extra_dirs = resolve_pipe_from_exports(pipe_code)
    except ValueError as exc:
        typer.secho(
            f"Ambiguous pipe code '{pipe_code}': {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc
    if extra_dirs:
        if library_dir is None:
            library_dir = extra_dirs
        else:
            library_dir = [*extra_dirs, *library_dir]

    execute_run(
        pipe_code=pipe_code,
        bundle_path=None,
        inputs=inputs,
        save_working_memory=save_working_memory,
        working_memory_path=working_memory_path,
        save_main_stuff=save_main_stuff,
        no_pretty_print=no_pretty_print,
        graph=graph,
        graph_full_data=graph_full_data,
        output_dir=output_dir,
        dry_run=dry_run,
        mock_inputs=mock_inputs,
        library_dir=library_dir,
        cost_report=cost_report,
        telemetry_command_label=f"{COMMAND} pipe",
        temporal=temporal,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        save_csv=save_csv,
    )
