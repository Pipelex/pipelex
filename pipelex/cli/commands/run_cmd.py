from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.hub import get_console, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "run"


def run_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run, can be omitted if you specify a bundle (.plx) that declares a main pipe"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - runs its main_pipe unless you specify a pipe code"),
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
        bool,
        typer.Option("--graph/--no-graph", help="Enable/disable execution graph outputs (JSON, Mermaid, HTML)"),
    ] = True,
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
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files). Can be specified multiple times."),
    ] = None,
) -> None:
    """Execute a pipeline from a specific bundle file (or not), specifying its pipe code or not.
    If the bundle is provided, it will run its main pipe unless you specify a pipe code.
    If the pipe code is provided, you don't need to provide a bundle file if it's already part of the imported packages.

    Examples:
        pipelex run my_pipe
        pipelex run --bundle my_bundle.plx
        pipelex run --bundle my_bundle.plx --pipe my_pipe
        pipelex run --pipe my_pipe --inputs data.json
        pipelex run my_bundle.plx --inputs data.json
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
        if target.endswith(".plx"):
            bundle_path = target
            if bundle:
                typer.secho(
                    "Failed to run: cannot use option --bundle if you're already passing a bundle file (.plx) as positional argument",
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
        plx_content: str | None = None
        if bundle_path:
            try:
                plx_content = Path(bundle_path).read_text(encoding="utf-8")
                validate_bundle_result = await validate_bundle(plx_content=plx_content)
                if not pipe_code:
                    main_pipe_code = validate_bundle_result.blueprints[0].main_pipe
                    if not main_pipe_code:
                        typer.secho(f"Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    pipe_code = main_pipe_code
                    source_description = f"bundle '{bundle_path}' • main pipe: '{pipe_code}'"
                else:
                    source_description = f"bundle '{bundle_path}' • pipe: '{pipe_code}'"
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except ValidateBundleError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipeInputError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
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
        typer.secho(f"\n🚀 Executing {source_description}...\n", fg=typer.colors.GREEN, bold=True)

        # Determine pipe run mode
        pipe_run_mode = PipeRunMode.DRY if dry_run else None

        # Build effective execution config with CLI overrides
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
            generate_graph=graph,
            force_include_full_data=graph_full_data,
            mock_inputs=mock_inputs or None,
        )

        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                plx_content=plx_content,
                bundle_uri=bundle_path,
                inputs=pipeline_inputs,
                pipe_run_mode=pipe_run_mode,
                execution_config=execution_config,
                library_dirs=library_dir,
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

        # Pretty print main_stuff unless disabled
        if not no_pretty_print:
            title = f"Final output of pipe [red]{pipe_code}[/red]"
            pipe_output.main_stuff.pretty_print_stuff(title=title)
            # TODO: no_pretty_print should also disable the pretty printing of each pipe operator step

        # Determine if we need an output directory
        output_path: Path | None = None
        graph_spec = pipe_output.graph_spec
        needs_output_path = graph or save_main_stuff or save_working_memory

        if needs_output_path:
            output_path = Path(get_incremental_directory_path(base_path=output_dir, base_name=f"{pipe_code}_output"))
            output_path.mkdir(parents=True, exist_ok=True)

        # Save graph outputs if requested
        saved_graphs: list[str] = []
        if graph:
            if not graph_spec:
                typer.secho(f"Failed to save graphs: no graph specification found for pipe '{pipe_code}'", fg=typer.colors.RED, err=True)
                raise typer.Exit(1)
            if not output_path:
                typer.secho("Failed to save graphs: no output directory specified", fg=typer.colors.RED, err=True)
                raise typer.Exit(1)

            # Generate all graph outputs
            graph_outputs = await generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=execution_config.graph_config,
                pipe_code=pipe_code,
            )

            # Save outputs to files (only those that were generated)
            if graph_outputs.graphspec_json is not None:
                graphspec_path = output_path / "graphspec.json"
                graphspec_path.write_text(graph_outputs.graphspec_json, encoding="utf-8")
                log.verbose(f"GraphSpec JSON saved to: {graphspec_path}")

            if graph_outputs.mermaidflow_mmd is not None:
                mermaidflow_mmd_path = output_path / "mermaidflow.mmd"
                mermaidflow_mmd_path.write_text(graph_outputs.mermaidflow_mmd, encoding="utf-8")
                log.verbose(f"Mermaidflow MMD saved to: {mermaidflow_mmd_path}")

            if graph_outputs.mermaidflow_html is not None:
                mermaidflow_html_path = output_path / "mermaidflow.html"
                mermaidflow_html_path.write_text(graph_outputs.mermaidflow_html, encoding="utf-8")
                log.verbose(f"Mermaidflow HTML saved to: {mermaidflow_html_path}")
                if "mermaidflow" not in saved_graphs:
                    saved_graphs.append("mermaidflow")

            if graph_outputs.reactflow_viewspec is not None:
                viewspec_path = output_path / "viewspec.json"
                viewspec_path.write_text(graph_outputs.reactflow_viewspec, encoding="utf-8")
                log.verbose(f"ReactFlow ViewSpec saved to: {viewspec_path}")

            if graph_outputs.reactflow_html is not None:
                reactflow_html_path = output_path / "reactflow.html"
                reactflow_html_path.write_text(graph_outputs.reactflow_html, encoding="utf-8")
                log.verbose(f"ReactFlow HTML saved to: {reactflow_html_path}")
                if "reactflow" not in saved_graphs:
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
        console.print("\n[green]✓[/green] [bold]Pipeline execution completed successfully[/bold]")
        if output_path:
            console.print(f"  Output saved to {output_path}:")
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

    except Exception as exc:
        log.error(f"Error executing pipeline: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
