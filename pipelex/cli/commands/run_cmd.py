from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME, DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.hub import get_console, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "run"


def run_cmd(
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
    """Execute a pipeline from a specific bundle file (or not), specifying its pipe code or not.
    If the bundle is provided, it will run its main pipe unless you specify a pipe code.
    If the pipe code is provided, you don't need to provide a bundle file if it's already part of the imported packages.
    If a directory is provided, it auto-detects bundle.mthds and inputs.json inside it.

    Examples:
        pipelex run my_pipe
        pipelex run --bundle my_bundle.mthds
        pipelex run --bundle my_bundle.mthds --pipe my_pipe
        pipelex run --pipe my_pipe --inputs data.json
        pipelex run my_bundle.mthds --inputs data.json
        pipelex run pipeline_01/
        pipelex run pipeline_01/ --pipe my_pipe
        pipelex run my_pipe --working-memory-path results.json --no-pretty-print
        pipelex run my_pipe --no-save-working-memory --no-save-main-stuff
        pipelex run my_pipe --no-graph                  # Disable graph generation
        pipelex run my_pipe --graph-full-data           # Force include full data in graph
        pipelex run my_pipe --graph-no-data             # Force exclude full data from graph
        pipelex run my_pipe --dry-run
        pipelex run my_pipe --dry-run --mock-inputs
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

    # Let's analyze the options and determine what pipe code to use and if we need to load a bundle
    pipe_code: str | None = None
    bundle_path: str | None = None

    # Determine source:
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

            # Find .mthds: try default name first, then fall back to single .mthds
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
                        f"Pass the .mthds file directly, e.g.: pipelex run {target_path / mthds_files[0].name}",
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

            # Add directory as library dir (prepend to user-supplied list)
            target_dir_str = str(target_path)
            if library_dir is None:
                library_dir = [target_dir_str]
            elif target_dir_str not in library_dir:
                library_dir = [target_dir_str, *library_dir]

            # Consume --pipe if provided
            if pipe:
                pipe_code = pipe
                pipe = None  # prevent double-assignment below

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

    async def run_pipeline(pipe_code: str | None = None, bundle_path: str | None = None):
        source_description: str
        mthds_content: str | None = None
        if bundle_path:
            try:
                mthds_content = Path(bundle_path).read_text(encoding="utf-8")
                # Use lightweight parsing to extract main_pipe without full validation
                # Full validation happens later during execute_pipeline
                if not pipe_code:
                    bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
                    main_pipe_code = bundle_blueprint.main_pipe
                    if not main_pipe_code:
                        msg = (
                            f"Bundle '{bundle_path}' does not declare a main_pipe. In order to run a bundle, "
                            "you must specify a main pipe in the bundle itself or specify a pipe code in the command line using the --pipe option."
                        )
                        typer.secho(msg, fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    pipe_code = main_pipe_code
                    source_description = f"bundle '{bundle_path}' • main pipe: '{pipe_code}'"
                else:
                    source_description = f"bundle '{bundle_path}' • pipe: '{pipe_code}'"
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except (PipelexInterpreterError, MthdsDecodeError) as exc:
                typer.secho(f"Failed to parse bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
        elif pipe_code:
            source_description = f"pipe '{pipe_code}'"
        else:
            typer.secho("Failed to run: no pipe code specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Load inputs if provided
        pipeline_inputs = None
        if inputs:
            if inputs.startswith("{"):
                pipeline_inputs = json.loads(inputs)
            else:
                try:
                    pipeline_inputs = load_json_dict_from_path(inputs)
                    typer.echo(f"Loaded inputs from: {inputs}")
                except FileNotFoundError as file_not_found_exc:
                    typer.secho(f"Failed to load input file '{inputs}': file not found", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from file_not_found_exc
                except JsonTypeError as json_type_error_exc:
                    typer.secho(f"Failed to parse input file '{inputs}': must be a valid JSON dictionary", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from json_type_error_exc

        # Execute pipeline
        inputs_description = f" with inputs '{inputs}'" if inputs and not inputs.startswith("{") else ""
        if dry_run:
            typer.secho(f"\n🧪 Dry-running {source_description}{inputs_description}...\n", fg=typer.colors.YELLOW, bold=True)
        else:
            typer.secho(f"\n🚀 Executing {source_description}{inputs_description}...\n", fg=typer.colors.GREEN, bold=True)

        # Determine pipe run mode
        pipe_run_mode = PipeRunMode.DRY if dry_run else None

        # Build effective execution config with CLI overrides
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
            generate_graph=graph,
            force_include_full_data=graph_full_data,
            mock_inputs=mock_inputs or None,
        )

        try:
            runner = PipelexRunner(
                bundle_uri=bundle_path,
                pipe_run_mode=pipe_run_mode,
                execution_config=execution_config,
                library_dirs=library_dir,
            )
            response = await runner.execute_pipeline(
                pipe_code=pipe_code,
                mthds_content=mthds_content,
                inputs=pipeline_inputs,
            )
            pipe_output = response.pipe_output
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline '{exc.pipe_code}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except PipelexError as exc:
            typer.secho(f"Failed to execute pipeline '{pipe_code or bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

        # Pretty print main_stuff unless disabled or in dry run mode
        if not no_pretty_print and not dry_run:
            title = f"Final output of pipe [red]{pipe_code}[/red]"
            pipe_output.main_stuff.pretty_print_stuff(title=title)
            # TODO: no_pretty_print should also disable the pretty printing of each pipe operator step

        # Determine if we need an output directory
        output_path: Path | None = None
        graph_spec = pipe_output.graph_spec
        needs_output_path = (graph_spec is not None) or save_main_stuff or save_working_memory

        if needs_output_path:
            output_path = Path(get_incremental_directory_path(base_path=output_dir, base_name=f"{pipe_code}_output"))
            output_path.mkdir(parents=True, exist_ok=True)

        # Save graph outputs if requested
        saved_graphs: list[str] = []
        if graph_spec:
            if not output_path:
                typer.secho("Failed to save graphs: no output directory specified", fg=typer.colors.RED, err=True)
                raise typer.Exit(1)

            # Generate all graph outputs
            graph_outputs = await generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=execution_config.graph_config,
                pipe_code=pipe_code,
            )

            # Save outputs to files
            saved_graph_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_path)
            for output_type in saved_graph_files:
                if "mermaidflow" in output_type and "mermaidflow" not in saved_graphs:
                    saved_graphs.append("mermaidflow")
                elif "reactflow" in output_type and "reactflow" not in saved_graphs:
                    saved_graphs.append("reactflow")

        # Save main_stuff files if enabled
        saved_main_stuff_formats: list[str] = []
        if save_main_stuff and output_path:
            main_stuff = pipe_output.working_memory.get_optional_main_stuff()
            if main_stuff:
                # Save JSON format
                main_stuff_json = await main_stuff.content.rendered_json_async()
                main_stuff_json_path = output_path / "main_stuff.json"
                main_stuff_json_path.write_text(main_stuff_json, encoding="utf-8")
                log.verbose(f"Main stuff JSON saved to: {main_stuff_json_path}")
                saved_main_stuff_formats.append("json")

                # Save Markdown format
                main_stuff_md = await main_stuff.content.rendered_markdown_async()
                main_stuff_md_path = output_path / "main_stuff.md"
                main_stuff_md_path.write_text(main_stuff_md, encoding="utf-8")
                log.verbose(f"Main stuff Markdown saved to: {main_stuff_md_path}")
                saved_main_stuff_formats.append("md")

                # Save pure HTML rendering
                main_stuff_html = await main_stuff.content.rendered_html_async()
                main_stuff_html_path = output_path / "main_stuff.html"
                main_stuff_html_path.write_text(main_stuff_html, encoding="utf-8")
                log.verbose(f"Main stuff HTML saved to: {main_stuff_html_path}")
                saved_main_stuff_formats.append("html")

                # Save HTML viewer (interactive viewer with format tabs)
                main_stuff_viewer = await render_stuff_viewer(main_stuff)
                main_stuff_viewer_path = output_path / "main_stuff_viewer.html"
                main_stuff_viewer_path.write_text(main_stuff_viewer, encoding="utf-8")
                log.verbose(f"Main stuff HTML viewer saved to: {main_stuff_viewer_path}")
                saved_main_stuff_formats.append("html_viewer")

        # Save working memory to JSON if enabled
        working_memory_output_path: str | None = None
        if save_working_memory and output_path:
            if working_memory_path:
                working_memory_output_path = working_memory_path
            else:
                working_memory_output_path = str(output_path / "working_memory.json")
            working_memory_dict = pipe_output.working_memory.smart_dump()
            save_as_json_to_path(object_to_save=working_memory_dict, path=working_memory_output_path)
            log.verbose(f"Working memory saved to: {working_memory_output_path}")

        # Print completion recap
        console = get_console()
        if dry_run:
            console.print("\n[yellow]✓[/yellow] [bold]Dry run completed successfully[/bold]")
        else:
            console.print("\n[green]✓[/green] [bold]Pipeline execution completed successfully[/bold]")
        if output_path:
            console.print(f"  Output saved to [bold magenta]{output_path}[/bold magenta]:")
            if saved_graphs:
                console.print(f"    [green]✓[/green] graphs: {', '.join(saved_graphs)}")
            if saved_main_stuff_formats:
                console.print(f"    [green]✓[/green] main_stuff: {', '.join(saved_main_stuff_formats)}")
            if working_memory_output_path:
                if Path(working_memory_output_path).is_relative_to(output_path):
                    console.print("    [green]✓[/green] working_memory.json")
                else:
                    console.print(f"    [green]✓[/green] working_memory: {working_memory_output_path}")

    # Initialize Pipelex BEFORE telemetry context to ensure proper setup
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)
            asyncio.run(run_pipeline(pipe_code=pipe_code, bundle_path=bundle_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN)

    except typer.Exit:
        raise

    except PipelexError as exc:
        console = get_console()
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print(f"  {exc.message}\n")
        raise typer.Exit(1) from exc

    except Exception as exc:
        log.error(f"Error executing pipeline: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
