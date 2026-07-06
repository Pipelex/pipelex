from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.commands.run._inputs_file_loader import find_default_inputs_file
from pipelex.cli.commands.run._run_core import COMMAND, execute_run, validate_run_flag_combination
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def run_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run (overrides bundle's main_pipe)"),
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
        str,
        typer.Option("--output-dir", "-o", help="Base directory for all outputs (working memory, main_stuff, graphs)"),
    ] = "results",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
    mock_usage: Annotated[
        bool,
        typer.Option(
            "--mock-usage",
            hidden=True,
            help="Internal test trigger: dry run whose LLM leaf mocks report nonzero synthetic usage so the cost report renders. Requires --dry-run.",
        ),
    ] = False,
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
    orchestrator: Annotated[
        str | None,
        typer.Option("--orchestrator", help="Boot this process under the named orchestrator plugin (e.g. 'temporal'); omit for in-process execution"),
    ] = None,
    dynamic_output_concept_ref: Annotated[
        str | None,
        typer.Option(
            "--dynamic-output-concept",
            "-O",
            help="Concept ref (e.g. 'document_qa.ReferenceCount') used to resolve a pipe whose output is declared as 'Dynamic'.",
        ),
    ] = None,
    costs: Annotated[
        bool | None,
        typer.Option(
            "--costs/--no-costs",
            help="Override config: emit usage (cost) tracing events and render the end-of-run cost report. Default on.",
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
    """Run a pipeline from a bundle file (.mthds) or pipeline directory.

    Examples:
        pipelex run bundle pipeline_01/
        pipelex run bundle pipeline_01/ --pipe my_pipe
        pipelex run bundle my_bundle.mthds
        pipelex run bundle my_bundle.mthds --pipe my_pipe --inputs data.json
        pipelex run bundle pipeline_01/ --dry-run
    """
    validate_run_flag_combination(dry_run=dry_run, mock_usage=mock_usage, mock_inputs=mock_inputs)

    pipe_code: str | None = pipe
    bundle_path: str | None = None
    target_path = Path(path)

    if target_path.is_dir():
        # Directory mode: auto-detect bundle and inputs
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                typer.secho(
                    f"Failed to run: no .mthds bundle file found in directory '{path}'",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                typer.secho(
                    f"Failed to run: multiple .mthds files found in '{path}' ({mthds_names}) "
                    f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly, e.g.: pipelex run bundle {target_path / mthds_files[0].name}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
            bundle_path = str(mthds_files[0])

        # Auto-detect inputs (inputs.json or inputs.toml) if --inputs not explicitly provided
        if not inputs:
            try:
                inputs_file = find_default_inputs_file(target_path)
            except AmbiguousInputsFilesError as ambiguity_exc:
                typer.secho(f"Failed to run: {ambiguity_exc.message}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from ambiguity_exc
            if inputs_file is not None:
                inputs = str(inputs_file)
                typer.echo(f"Auto-detected inputs: {inputs}")

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

        typer.echo(f"Auto-detected bundle: {bundle_path}")

    elif is_pipelex_file(target_path):
        bundle_path = path
    else:
        typer.secho(
            f"Failed to run: '{path}' is not a .mthds file or directory.\n"
            f"  To run a pipe by code, use: pipelex run pipe <code>\n"
            f"  To run a bundle, pass a .mthds file or directory: pipelex run bundle <path>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    execute_run(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        inputs=inputs,
        save_working_memory=save_working_memory,
        working_memory_path=working_memory_path,
        save_main_stuff=save_main_stuff,
        no_pretty_print=no_pretty_print,
        graph=graph,
        graph_full_data=graph_full_data,
        output_dir=output_dir,
        dry_run=dry_run,
        mock_usage=mock_usage,
        mock_inputs=mock_inputs,
        library_dir=library_dir,
        costs=costs,
        telemetry_command_label=f"{COMMAND} bundle",
        orchestrator=orchestrator,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        save_csv=save_csv,
    )
