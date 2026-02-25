from __future__ import annotations

from pathlib import Path
from typing import Annotated

import click
import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME, DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.commands.run._run_core import COMMAND, execute_run
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def run_pipe_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code, bundle file path (.mthds), or pipeline directory (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run, can be omitted if you specify a bundle (.mthds) that declares a main pipe"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.mthds) - runs its main_pipe unless you specify a pipe code"),
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
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
) -> None:
    """Run a pipe by code, bundle file (.mthds), or pipeline directory.

    Examples:
        pipelex run pipe my_pipe
        pipelex run pipe --bundle my_bundle.mthds
        pipelex run pipe --bundle my_bundle.mthds --pipe my_pipe
        pipelex run pipe --pipe my_pipe --inputs data.json
        pipelex run pipe my_bundle.mthds --inputs data.json
        pipelex run pipe pipeline_01/
        pipelex run pipe pipeline_01/ --pipe my_pipe
        pipelex run pipe my_pipe --dry-run
        pipelex run pipe my_pipe --dry-run --mock-inputs
    """
    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        typer.secho(
            "Failed to run: --mock-inputs requires --dry-run",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    pipe_code: str | None = None
    bundle_path: str | None = None

    # Determine source
    if target:
        target_path = Path(target)
        if target_path.is_dir():
            # Directory mode: auto-detect bundle and inputs
            if bundle:
                typer.secho(
                    "Failed to run: cannot use option --bundle when passing a pipeline directory as target",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)

            bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
            if bundle_file.is_file():
                bundle_path = str(bundle_file)
            else:
                mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
                if len(mthds_files) == 0:
                    typer.secho(
                        f"Failed to run: no .mthds bundle file found in directory '{target}'",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(1)
                if len(mthds_files) > 1:
                    mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                    typer.secho(
                        f"Failed to run: multiple .mthds files found in '{target}' ({mthds_names}) "
                        f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                        f"Pass the .mthds file directly, e.g.: pipelex run pipe {target_path / mthds_files[0].name}",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(1)
                bundle_path = str(mthds_files[0])

            # Auto-detect inputs if --inputs not explicitly provided
            inputs_file = target_path / DEFAULT_INPUTS_FILE_NAME
            if not inputs and inputs_file.is_file():
                inputs = str(inputs_file)
                typer.echo(f"Auto-detected inputs: {inputs}")

            # Add directory as library dir
            target_dir_str = str(target_path)
            if library_dir is None:
                library_dir = [target_dir_str]
            elif target_dir_str not in library_dir:
                library_dir = [target_dir_str, *library_dir]

            if pipe:
                pipe_code = pipe
                pipe = None

            typer.echo(f"Auto-detected bundle: {bundle_path}")

        elif is_pipelex_file(target_path):
            bundle_path = target
            if bundle:
                typer.secho(
                    "Failed to run: cannot use option --bundle if you're already passing a bundle file (.mthds) as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to run: cannot use option --pipe if you're already passing a pipe code as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)

    if bundle:
        assert not bundle_path, "bundle_path should be None at this stage if --bundle is provided"
        bundle_path = bundle

    if pipe:
        assert not pipe_code, "pipe_code should be None at this stage if --pipe is provided"
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        typer.secho("Failed to run: no pipe code or bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # If running a bare pipe code, check installed methods' exports for additional library dirs
    if pipe_code and not bundle_path:
        extra_dirs = resolve_pipe_from_exports(pipe_code)
        if extra_dirs:
            if library_dir is None:
                library_dir = extra_dirs
            else:
                library_dir = [*extra_dirs, *library_dir]

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
        mock_inputs=mock_inputs,
        library_dir=library_dir,
        telemetry_command_label=f"{COMMAND} pipe",
    )
