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
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.hub import get_console, get_telemetry_manager
from pipelex.observability.graphspec import (
    GraphSpec,
    GraphTracer,
    GraphTracerManager,
    graphspec_to_dataflow_mermaid,
    graphspec_to_mermaid,
    save_graphspec,
)
from pipelex.observability.graphspec.html_renderer import render_mermaid_html_async
from pipelex.observability.graphspec.mermaid import VALID_DIRECTIONS
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import get_incremental_file_path
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
    graph_json: Annotated[
        str | None,
        typer.Option("--graph-json", help="Path to save execution graph as JSON"),
    ] = None,
    graph_mermaid: Annotated[
        str | None,
        typer.Option("--graph-mermaid", help="Path to save execution graph as Mermaid (.mmd)"),
    ] = None,
    graph_html: Annotated[
        str | None,
        typer.Option("--graph-html", help="Path to save execution graph as HTML"),
    ] = None,
    graph_data_flow: Annotated[
        bool,
        typer.Option("--graph-data-flow", help="Use data flow view instead of orchestration view"),
    ] = False,
    graph_direction: Annotated[
        str,
        typer.Option("--graph-direction", help=f"Mermaid direction ({', '.join(sorted(VALID_DIRECTIONS))})"),
    ] = "TD",
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
        pipelex run my_pipe --graph-json execution.json --graph-mermaid execution.mmd
        pipelex run my_pipe --graph-html dataflow.html --graph-data-flow
    """
    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Validate graph direction
    if graph_direction not in VALID_DIRECTIONS:
        typer.secho(
            f"Invalid graph direction '{graph_direction}'. Must be one of: {', '.join(sorted(VALID_DIRECTIONS))}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Determine if graph tracing is requested
    generate_graph = any([graph_json, graph_mermaid, graph_html])

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

        # Set up graph tracing if requested
        graph_spec: GraphSpec | None = None
        graph_context = None
        manager: GraphTracerManager | None = None

        if generate_graph:
            tracer = GraphTracer()
            graph_manager = GraphTracerManager(tracer)
            manager = graph_manager
            graph_id = PipelineFactory.make_pipeline_run_id()
            graph_context = graph_manager.setup(
                graph_id=graph_id,
                pipeline_ref_main_pipe=pipe_code,
            )

        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                inputs=pipeline_inputs,
                graph_context=graph_context,
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        finally:
            # Teardown graph tracing (capture graph even on failure)
            if manager is not None:
                graph_spec = manager.teardown()

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
        if graph_spec is not None:
            if graph_json:
                save_graphspec(graph_spec, Path(graph_json))
                typer.secho(f"✅ Graph JSON saved to: {graph_json}", fg=typer.colors.GREEN)

            if graph_mermaid or graph_html:
                # Generate Mermaid code
                if graph_data_flow:
                    # Data flow view: default to LR if user didn't override direction
                    effective_direction = graph_direction if graph_direction != "TD" else "LR"
                    mermaid_code = graphspec_to_dataflow_mermaid(graph_spec, direction=effective_direction)
                else:
                    # Orchestration view (default)
                    mermaid_code = graphspec_to_mermaid(graph_spec, direction=graph_direction)

                if graph_mermaid:
                    Path(graph_mermaid).write_text(mermaid_code, encoding="utf-8")
                    typer.secho(f"✅ Graph Mermaid saved to: {graph_mermaid}", fg=typer.colors.GREEN)

                if graph_html:
                    title = f"Execution: {pipe_code}" if pipe_code else "Pipeline Execution"
                    html_content = await render_mermaid_html_async(mermaid_code, title=title)
                    Path(graph_html).write_text(html_content, encoding="utf-8")
                    typer.secho(f"✅ Graph HTML saved to: {graph_html}", fg=typer.colors.GREEN)

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
