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
from pipelex.graph.graph_config import DataInclusion
from pipelex.graph.graphspec_io import save_graphspec
from pipelex.graph.mermaid import (
    graphspec_to_combo_mermaid,
    graphspec_to_combo_mermaid_with_data,
    graphspec_to_dataflow_mermaid,
    graphspec_to_dataflow_mermaid_with_data,
    graphspec_to_orchestration_mermaid,
)
from pipelex.hub import get_console, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.file_utils import get_incremental_directory_path, get_incremental_file_path
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path
from pipelex.tools.misc.mermaid_utils import render_mermaid_html_async, render_mermaid_html_with_data_async
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
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save output JSON, default to '{pipe_code}.json'"),
    ] = None,
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving output to file"),
    ] = False,
    no_pretty_print: Annotated[
        bool,
        typer.Option("--no-pretty-print", help="Skip pretty printing the main_stuff"),
    ] = False,
    graph: Annotated[
        bool | None,
        typer.Option("--graph/--no-graph", help="Generate execution graph outputs (JSON, Mermaid, HTML for both orchestration and data flow views)"),
    ] = None,
    graph_dir: Annotated[
        str | None,
        typer.Option("--graph-dir", help="Base directory for graph output (default: results)"),
    ] = None,
    graph_name: Annotated[
        str | None,
        typer.Option("--graph-name", help="Base name for graph directory (default: {pipe_code}_graph)"),
    ] = None,
    graph_full_data: Annotated[
        bool,
        typer.Option("--graph-full-data", help="Include full serialized input/output data in graph (requires --graph)"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
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
        pipelex run my_pipe --output results.json --no-pretty-print
        pipelex run my_pipe --graph
        pipelex run my_pipe --graph --graph-dir ./analysis
        pipelex run my_pipe --graph --graph-full-data
        pipelex run my_pipe --dry-run
    """
    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

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
        if bundle_path:
            try:
                validate_bundle_result = await validate_bundle(plx_file_path=bundle_path)
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
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_overrides(
            generate_graph=graph,
            include_full_data=graph_full_data or None,
        )
        effective_full_data = execution_config.graph_config.data_inclusion.get(DataInclusion.STUFF_JSON_CONTENT, False)

        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                inputs=pipeline_inputs,
                pipe_run_mode=pipe_run_mode,
                execution_config=execution_config,
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

        # Pretty print main_stuff unless disabled
        if not no_pretty_print:
            title = f"Final output of pipe [red]{pipe_code}[/red]"
            pipe_output.main_stuff.pretty_print_stuff(title=title)
            # TODO: no_pretty_print should also disable the pretty printing of each pipe operator step

        # Save working memory to JSON unless disabled
        if not no_output:
            output_path = output or get_incremental_file_path(
                base_path="results",
                base_name=f"run_{pipe_code}",
                extension="json",
            )
            working_memory_dict = pipe_output.working_memory.smart_dump()
            save_as_json_to_path(object_to_save=working_memory_dict, path=output_path)
            typer.secho(f"✅ Working memory saved to: {output_path}", fg=typer.colors.GREEN)

        # Save graph outputs if requested
        if graph_spec := pipe_output.graph_spec:
            # Create output directory with incremental numbering
            base_dir = graph_dir or "results"
            dir_name = graph_name or f"{pipe_code}_graph"
            graph_output_dir = Path(get_incremental_directory_path(base_path=base_dir, base_name=dir_name))

            # Save JSON
            save_graphspec(graph_spec, graph_output_dir / "graph.json")
            typer.secho(f"\n✅ Graph JSON saved to: {graph_output_dir / 'graph.json'}", fg=typer.colors.GREEN)

            # Generate orchestration view (top-down)
            orch_mermaid = graphspec_to_orchestration_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
            (graph_output_dir / "orchestration.mmd").write_text(orch_mermaid, encoding="utf-8")
            typer.secho(f"✅ Orchestration Mermaid saved to: {graph_output_dir / 'orchestration.mmd'}", fg=typer.colors.GREEN)

            orch_html = await render_mermaid_html_async(orch_mermaid, title=f"Orchestration: {pipe_code}")
            (graph_output_dir / "orchestration.html").write_text(orch_html, encoding="utf-8")
            typer.secho(f"✅ Orchestration HTML saved to: {graph_output_dir / 'orchestration.html'}", fg=typer.colors.GREEN)

            # Generate data flow view (top-down)
            if effective_full_data:
                dataflow_with_data = graphspec_to_dataflow_mermaid_with_data(graph_spec, direction=FlowchartDirection.TOP_DOWN)
                dataflow_mermaid = dataflow_with_data.mermaid_code
                (graph_output_dir / "dataflow.mmd").write_text(dataflow_mermaid, encoding="utf-8")
                typer.secho(f"✅ Data flow Mermaid saved to: {graph_output_dir / 'dataflow.mmd'}", fg=typer.colors.GREEN)

                dataflow_html = await render_mermaid_html_with_data_async(
                    dataflow_mermaid,
                    stuff_data=dataflow_with_data.stuff_data,
                    title=f"Data Flow: {pipe_code}",
                )
                (graph_output_dir / "dataflow.html").write_text(dataflow_html, encoding="utf-8")
                typer.secho(f"✅ Data flow HTML (interactive) saved to: {graph_output_dir / 'dataflow.html'}", fg=typer.colors.GREEN)
            else:
                dataflow_mermaid = graphspec_to_dataflow_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
                (graph_output_dir / "dataflow.mmd").write_text(dataflow_mermaid, encoding="utf-8")
                typer.secho(f"✅ Data flow Mermaid saved to: {graph_output_dir / 'dataflow.mmd'}", fg=typer.colors.GREEN)

                dataflow_html = await render_mermaid_html_async(dataflow_mermaid, title=f"Data Flow: {pipe_code}")
                (graph_output_dir / "dataflow.html").write_text(dataflow_html, encoding="utf-8")
                typer.secho(f"✅ Data flow HTML saved to: {graph_output_dir / 'dataflow.html'}", fg=typer.colors.GREEN)

            # Generate combo view (top-down, data flow with controller subgraphs)
            if effective_full_data:
                combo_with_data = graphspec_to_combo_mermaid_with_data(graph_spec, direction=FlowchartDirection.TOP_DOWN)
                combo_mermaid = combo_with_data.mermaid_code
                (graph_output_dir / "combo.mmd").write_text(combo_mermaid, encoding="utf-8")
                typer.secho(f"✅ Combo Mermaid saved to: {graph_output_dir / 'combo.mmd'}", fg=typer.colors.GREEN)

                combo_html = await render_mermaid_html_with_data_async(
                    combo_mermaid,
                    stuff_data=combo_with_data.stuff_data,
                    title=f"Combo: {pipe_code}",
                )
                (graph_output_dir / "combo.html").write_text(combo_html, encoding="utf-8")
                typer.secho(f"✅ Combo HTML (interactive) saved to: {graph_output_dir / 'combo.html'}", fg=typer.colors.GREEN)
            else:
                combo_mermaid = graphspec_to_combo_mermaid(graph_spec, direction=FlowchartDirection.TOP_DOWN)
                (graph_output_dir / "combo.mmd").write_text(combo_mermaid, encoding="utf-8")
                typer.secho(f"✅ Combo Mermaid saved to: {graph_output_dir / 'combo.mmd'}", fg=typer.colors.GREEN)

                combo_html = await render_mermaid_html_async(combo_mermaid, title=f"Combo: {pipe_code}")
                (graph_output_dir / "combo.html").write_text(combo_html, encoding="utf-8")
                typer.secho(f"✅ Combo HTML saved to: {graph_output_dir / 'combo.html'}", fg=typer.colors.GREEN)

            typer.secho(f"\n📊 All graph outputs saved to: {graph_output_dir}", fg=typer.colors.CYAN, bold=True)

        typer.secho("✅ Pipeline execution completed successfully", fg=typer.colors.GREEN)

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
