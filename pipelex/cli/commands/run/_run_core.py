from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from posthog import tag

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.run._inputs_path_resolver import resolve_inputs_paths
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
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


async def _execute_run(
    pipe_code: str | None,
    bundle_path: str | None,
    inputs: str | None,
    save_working_memory: bool,
    working_memory_path: str | None,
    save_main_stuff: bool,
    no_pretty_print: bool,
    graph: bool | None,
    graph_full_data: bool | None,
    output_dir: str,
    dry_run: bool,
    mock_inputs: bool,
    library_dir: list[str] | None,
) -> None:
    """Core async execution logic for running a pipe.

    Shared between the ``method`` and ``pipe`` subcommands.
    """
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
        except FileNotFoundError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except (PipelexInterpreterError, MthdsDecodeError) as exc:
            typer.secho(f"Failed to parse bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
    elif not pipe_code:
        typer.secho("Failed to run: no pipe code specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Load inputs if provided
    pipeline_inputs = None
    if inputs:
        if inputs.startswith("{"):
            try:
                pipeline_inputs = json.loads(inputs)
            except json.JSONDecodeError as json_decode_exc:
                typer.secho(f"Failed to parse inline JSON inputs: {json_decode_exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from json_decode_exc
        else:
            try:
                pipeline_inputs = load_json_dict_from_path(inputs)
                # Resolve relative url paths against the inputs file's parent directory
                base_dir = Path(inputs).parent.resolve()
                pipeline_inputs = resolve_inputs_paths(pipeline_inputs, base_dir)
                typer.echo(f"Loaded inputs from: {inputs}")
            except FileNotFoundError as file_not_found_exc:
                typer.secho(f"Failed to load input file '{inputs}': file not found", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from file_not_found_exc
            except JsonTypeError as json_type_error_exc:
                typer.secho(f"Failed to parse input file '{inputs}': must be a valid JSON dictionary", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from json_type_error_exc

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

        graph_outputs = await generate_graph_outputs(
            graph_spec=graph_spec,
            graph_config=execution_config.graph_config,
            pipe_code=pipe_code,
        )

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
            main_stuff_json = await main_stuff.content.rendered_json_async()
            main_stuff_json_path = output_path / "main_stuff.json"
            main_stuff_json_path.write_text(main_stuff_json, encoding="utf-8")
            log.verbose(f"Main stuff JSON saved to: {main_stuff_json_path}")
            saved_main_stuff_formats.append("json")

            main_stuff_md = await main_stuff.content.rendered_markdown_async()
            main_stuff_md_path = output_path / "main_stuff.md"
            main_stuff_md_path.write_text(main_stuff_md, encoding="utf-8")
            log.verbose(f"Main stuff Markdown saved to: {main_stuff_md_path}")
            saved_main_stuff_formats.append("md")

            main_stuff_html = await main_stuff.content.rendered_html_async()
            main_stuff_html_path = output_path / "main_stuff.html"
            main_stuff_html_path.write_text(main_stuff_html, encoding="utf-8")
            log.verbose(f"Main stuff HTML saved to: {main_stuff_html_path}")
            saved_main_stuff_formats.append("html")

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


def execute_run(
    pipe_code: str | None,
    bundle_path: str | None,
    inputs: str | None,
    save_working_memory: bool,
    working_memory_path: str | None,
    save_main_stuff: bool,
    no_pretty_print: bool,
    graph: bool | None,
    graph_full_data: bool | None,
    output_dir: str,
    dry_run: bool,
    mock_inputs: bool,
    library_dir: list[str] | None,
    telemetry_command_label: str = COMMAND,
) -> None:
    """Synchronous entry point that wraps the async execution with Pipelex setup/teardown.

    Shared between the ``method`` and ``pipe`` subcommands.
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN, library_dirs=library_dir)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=telemetry_command_label)
            asyncio.run(
                _execute_run(
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
                )
            )

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
