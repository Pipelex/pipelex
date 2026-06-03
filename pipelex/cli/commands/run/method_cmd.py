from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.run._run_core import COMMAND, execute_run
from pipelex.cli.method_resolver import resolve_method_target


def run_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method to run"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run (overrides method's main_pipe)"),
    ] = None,
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
        str | None,
        typer.Option("--output-dir", "-o", help="Base directory for all outputs (working memory, main_stuff, graphs)"),
    ] = None,
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
            help="Write the main stuff to this literal CSV path (not under --output-dir; absolute/~/relative ok). Requires a flat list output.",
        ),
    ] = None,
) -> None:
    """Run an installed method by name.

    Resolves the method from ~/.mthds/methods/ or .mthds/methods/,
    determines the pipe to execute (using --pipe or the method's main_pipe),
    and runs it.

    Examples:
        pipelex run method my-method
        pipelex run method my-method --pipe custom_pipe
        pipelex run method my-method --inputs data.json
        pipelex run method my-method --dry-run
    """
    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        typer.secho(
            "Failed to run: --mock-inputs requires --dry-run",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Resolve method name to pipe_code and library dirs
    pipe_code, method_library_dirs, _ = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )

    method_dir = Path(method_library_dirs[0])

    # Default output_dir to a results/ folder inside the method's directory
    effective_output_dir = output_dir or str(method_dir / "results")

    # Resolve --inputs relative to the method's directory
    effective_inputs: str | None = inputs
    if inputs and not inputs.startswith("{"):
        inputs_path = Path(inputs)
        if not inputs_path.is_absolute():
            effective_inputs = str(method_dir / inputs_path)

    # Merge method library dirs with user-supplied -L dirs
    if library_dir:
        effective_library_dir = [*method_library_dirs, *library_dir]
    else:
        effective_library_dir = method_library_dirs

    execute_run(
        pipe_code=pipe_code,
        bundle_path=None,
        inputs=effective_inputs,
        save_working_memory=save_working_memory,
        working_memory_path=working_memory_path,
        save_main_stuff=save_main_stuff,
        no_pretty_print=no_pretty_print,
        graph=graph,
        graph_full_data=graph_full_data,
        output_dir=effective_output_dir,
        dry_run=dry_run,
        mock_inputs=mock_inputs,
        library_dir=effective_library_dir,
        cost_report=cost_report,
        telemetry_command_label=f"{COMMAND} method",
        temporal=temporal,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        save_csv=save_csv,
    )
