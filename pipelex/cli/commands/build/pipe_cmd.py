import asyncio
import os
import time
from pathlib import Path
from typing import Annotated

import typer
from posthog import tag

from pipelex import log
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME
from pipelex.builder.runner_code import generate_runner_code
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.build.structures_cmd import generate_structures_from_blueprints
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.graph.graph_config import GraphConfig
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import get_console, get_report_delegate, get_required_pipe, get_telemetry_manager
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import PACKAGE_VERSION, Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    get_incremental_directory_path,
    get_incremental_file_path,
    save_text_to_path,
)
from pipelex.tools.misc.json_utils import save_as_json_to_path
from pipelex.tools.misc.pretty import PrettyPrinter

COMMAND = "build"
SUB_COMMAND_PIPE = "pipe"


async def _save_graph_outputs_to_dir(
    graph_spec: GraphSpec,
    graph_config: GraphConfig,
    pipe_code: str,
    output_dir: Path,
) -> list[str]:
    """Save graph outputs to a directory.

    Args:
        graph_spec: The graph specification to render.
        graph_config: Configuration for graph generation.
        pipe_code: The pipe code for use in titles.
        output_dir: Directory where graph files will be saved.

    Returns:
        List of saved graph format names (e.g., "mermaidflow", "reactflow").
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_outputs = await generate_graph_outputs(
        graph_spec=graph_spec,
        graph_config=graph_config,
        pipe_code=pipe_code,
    )

    saved_formats: list[str] = []
    if graph_outputs.graphspec_json is not None:
        (output_dir / "graphspec.json").write_text(graph_outputs.graphspec_json, encoding="utf-8")
        log.verbose(f"GraphSpec JSON saved to: {output_dir / 'graphspec.json'}")

    if graph_outputs.mermaidflow_mmd is not None:
        (output_dir / "mermaidflow.mmd").write_text(graph_outputs.mermaidflow_mmd, encoding="utf-8")
        log.verbose(f"Mermaidflow Mermaid saved to: {output_dir / 'mermaidflow.mmd'}")

    if graph_outputs.mermaidflow_html is not None:
        (output_dir / "mermaidflow.html").write_text(graph_outputs.mermaidflow_html, encoding="utf-8")
        log.verbose(f"Mermaidflow HTML saved to: {output_dir / 'mermaidflow.html'}")
        saved_formats.append("mermaidflow")

    if graph_outputs.reactflow_viewspec is not None:
        (output_dir / "viewspec.json").write_text(graph_outputs.reactflow_viewspec, encoding="utf-8")
        log.verbose(f"ReactFlow ViewSpec saved to: {output_dir / 'viewspec.json'}")

    if graph_outputs.reactflow_html is not None:
        (output_dir / "reactflow.html").write_text(graph_outputs.reactflow_html, encoding="utf-8")
        log.verbose(f"ReactFlow HTML saved to: {output_dir / 'reactflow.html'}")
        saved_formats.append("reactflow")

    return saved_formats


"""
Today's example:
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch and some brand guidelines"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch and some brand guidelines, \
    include 3 variants of the ideas and 2 variants of each prompt"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch \
    and some brand guidelines, propose 2 different ideas, and for each, 3 style variants in the image generation prompt, \
        at the end we want the rendered image" -o mascot

pipelex build pipe "Given an expense report, apply company rules"
pipelex build pipe "Take a CV, a Job offer text, and analyze if they match"
pipelex build pipe "Take a CV and a Job offer text, analyze if they match and generate 5 questions for the interview"
pipelex build pipe "Take a CV and a Job offer, analyze if they match and generate 5 questions for the interview"

pipelex build pipe \
    "Take a Job offer text and a bunch of CVs, analyze how each CV matches the Job offer and generate 5 questions for each interview"

pipelex build pipe \
    "Take a Job offer and a bunch of CVs, analyze how each CV matches the Job offer and generate 5 questions for each interview"

# Other ideas:
pipelex build pipe "Take a photo as input, and render the opposite of the photo, don't structure anything, use only text content, be super concise"
pipelex build pipe "Take a photo as input, and render the opposite of the photo"
pipelex build pipe "Given an RDFP, build a compliance matrix"
pipelex build pipe "Given a theme, write a Haiku"
"""


def build_pipe_cmd(
    prompt: Annotated[
        str,
        typer.Argument(help="Prompt describing what the pipeline should do"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
    output_name: Annotated[
        str | None,
        typer.Option("--output-name", "-o", help="Base name for the generated file or directory (without extension)"),
    ] = None,
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", help="Directory where files will be generated"),
    ] = None,
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
    no_extras: Annotated[
        bool,
        typer.Option("--no-extras", help="Skip generating inputs.json and runner.py, only generate the PLX file"),
    ] = False,
    bundle_view: Annotated[
        bool,
        typer.Option("--bundle-view/--no-bundle-view", help="Generate bundle view HTML and SVG files"),
    ] = False,
    graph: Annotated[
        bool | None,
        typer.Option("--graph/--no-graph", help="Generate execution graphs for both build process and built pipeline"),
    ] = None,
    graph_full_data: Annotated[
        bool | None,
        typer.Option(
            "--graph-full-data/--graph-no-data",
            help="Override config: include or exclude full serialized data in graphs (requires --graph)",
        ),
    ] = None,
) -> None:
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_PIPE)

    typer.secho("Building pipeline...\n", fg=typer.colors.GREEN, bold=True)

    async def run_pipeline():
        start_time = time.time()
        # Get builder config
        builder_config = get_config().pipelex.builder_config

        # Case 1: --no-output flag → Don't save anything
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)

        # Build execution config with graph overrides if --graph is enabled
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
            generate_graph=graph,
            force_include_full_data=graph_full_data,
        )

        # Build the pipeline
        builder_loop = BuilderLoop()
        try:
            pipelex_bundle_spec, builder_graph_spec = await builder_loop.build_and_fix(
                builder_pipe=builder_pipe, inputs={"brief": prompt}, execution_config=execution_config, output_dir=output_dir
            )
        except PipeBuilderError as exc:
            msg = f"Builder loop: Failed to execute pipeline: {exc}."
            if exc.working_memory:
                failure_memory_path = get_incremental_file_path(
                    base_path=builder_config.default_output_dir,
                    base_name="failure_memory",
                    extension="json",
                )
                save_as_json_to_path(object_to_save=exc.working_memory.smart_dump(), path=str(failure_memory_path))
                typer.secho(f"❌ {msg}", fg=typer.colors.RED)
                typer.secho(f"❌ Failure memory saved to: {failure_memory_path}", fg=typer.colors.RED)
            else:
                typer.secho(f"❌ {msg}", fg=typer.colors.RED)
                typer.secho("❌ No failure memory available", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Return early if no output requested
        if no_output:
            return

        # Determine base output directory
        base_dir = output_dir or builder_config.default_output_dir

        # Determine output path and whether to generate extras
        bundle_file_name = Path(f"{builder_config.default_bundle_file_name}.plx")

        if no_extras:
            # Generate single file: {base_dir}/{name}_01.plx
            name = output_name or builder_config.default_bundle_file_name
            plx_file_path = get_incremental_file_path(
                base_path=base_dir,
                base_name=name,
                extension="plx",
            )
            extras_output_dir = ""  # Not used in no_extras mode
        else:
            # Generate directory with extras: {base_dir}/{name}_01/bundle.plx + extras
            dir_name = output_name or builder_config.default_directory_base_name
            extras_output_dir = get_incremental_directory_path(
                base_path=base_dir,
                base_name=dir_name,
            )
            plx_file_path = Path(extras_output_dir) / bundle_file_name

        # Save the PLX file
        ensure_directory_for_file_path(file_path=str(plx_file_path))
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=str(plx_file_path))
        log.verbose(f"Pipelex bundle saved to: {plx_file_path}")

        if no_extras:
            end_time = time.time()
            console = get_console()
            console.print(f"\n[green]✓[/green] [bold]Pipeline built successfully ({end_time - start_time:.1f}s)[/bold]")
            console.print(f"  Output: {plx_file_path}")
            return

        # Generate extras (inputs and runner)
        if not no_extras:
            main_pipe_code = pipelex_bundle_spec.main_pipe
            domain_code = pipelex_bundle_spec.domain
            if main_pipe_code:
                saved_bundle_view_formats: list[str] = []
                saved_structure_names: list[str] = []
                saved_graph_sections: list[tuple[str, list[str]]] = []

                try:
                    if bundle_view:
                        pretty = pipelex_bundle_spec.rendered_pretty()
                        # Generate pretty HTML
                        pretty_html = PrettyPrinter.pretty_html(pretty=pretty)
                        html_path = os.path.join(extras_output_dir, "bundle_view.html")
                        save_text_to_path(text=pretty_html, path=html_path)
                        log.verbose(f"Pretty HTML saved to: {html_path}")
                        saved_bundle_view_formats.append("html")

                        # Generate pretty SVG
                        pretty_svg = PrettyPrinter.pretty_svg(pretty=pretty)
                        svg_path = os.path.join(extras_output_dir, "bundle_view.svg")
                        save_text_to_path(text=pretty_svg, path=svg_path)
                        log.verbose(f"Pretty SVG saved to: {svg_path}")
                        saved_bundle_view_formats.append("svg")

                    pipe = get_required_pipe(pipe_code=main_pipe_code)

                    # Generate structures folder FIRST (before runner, since runner imports from structures)
                    structures_output_dir = Path(extras_output_dir) / "structures"
                    generated_structures = generate_structures_from_blueprints(
                        blueprints=[pipelex_bundle_spec.to_blueprint()],
                        output_directory=structures_output_dir,
                        skip_existing_check=True,
                        quiet=True,
                    )
                    if generated_structures:
                        saved_structure_names = [concept_code for _, concept_code in generated_structures]
                        log.verbose(f"Generated {len(generated_structures)} structure(s) in: {structures_output_dir}")

                    # Generate inputs.json (only if the pipe has inputs)
                    has_inputs = not pipe.inputs.is_empty
                    if has_inputs:
                        inputs_json_str = pipe.inputs.render_inputs(indent=2)
                        inputs_json_path = os.path.join(extras_output_dir, DEFAULT_INPUTS_FILE_NAME)
                        save_text_to_path(text=inputs_json_str, path=inputs_json_path)
                        log.verbose(f"Inputs template saved to: {inputs_json_path}")

                    # Determine if output is a list from the bundle spec
                    main_pipe_spec = pipelex_bundle_spec.pipe[main_pipe_code] if pipelex_bundle_spec.pipe else None
                    output_is_list = False
                    if main_pipe_spec:
                        output_parse = parse_concept_with_multiplicity(main_pipe_spec.output)
                        output_is_list = output_parse.multiplicity is not None

                    # Generate runner.py (after structures are generated)
                    runner_code = generate_runner_code(pipe, output_multiplicity=output_is_list, library_dir=extras_output_dir)
                    runner_path = os.path.join(extras_output_dir, f"run_{main_pipe_code}.py")
                    save_text_to_path(text=runner_code, path=runner_path)
                    log.verbose(f"Python runner script saved to: {runner_path}")

                    # Generate empty __init__.py to make it a proper Python package
                    init_path = os.path.join(extras_output_dir, "__init__.py")
                    save_text_to_path(text="", path=init_path)
                    log.verbose(f"Package init file saved to: {init_path}")

                    get_report_delegate().generate_report()

                    # Generate graphs if it was tracked during the build process
                    if builder_graph_spec:
                        # Save builder pipeline graph in graphs/ subfolder
                        graphs_dir = Path(extras_output_dir) / "graphs"
                        builder_graph_dir = graphs_dir / "builder_graph"
                        builder_graph_formats = await _save_graph_outputs_to_dir(
                            graph_spec=builder_graph_spec,
                            graph_config=execution_config.graph_config,
                            pipe_code=builder_pipe,
                            output_dir=builder_graph_dir,
                        )
                        if builder_graph_formats:
                            saved_graph_sections.append(("builder", builder_graph_formats))

                        # Run built pipeline in dry-run mode to generate its graph
                        try:
                            built_pipe_execution_config = execution_config.with_graph_config_overrides(mock_inputs=True)

                            # pass empty library_dirs to avoid loading any libraries set at env var or instance level:
                            # we don't want any other pipeline to interfere with the pipeline we just built
                            built_pipe_output = await execute_pipeline(
                                plx_content=plx_content,
                                pipe_run_mode=PipeRunMode.DRY,
                                execution_config=built_pipe_execution_config,
                                library_dirs=[],
                            )
                            if built_pipe_output.graph_spec:
                                pipeline_graph_dir = graphs_dir / "pipeline_graph"
                                log.verbose(f"Saving pipeline graph for pipe {main_pipe_code} to {pipeline_graph_dir}")
                                pipeline_graph_formats = await _save_graph_outputs_to_dir(
                                    graph_spec=built_pipe_output.graph_spec,
                                    graph_config=execution_config.graph_config,
                                    pipe_code=main_pipe_code,
                                    output_dir=pipeline_graph_dir,
                                )
                                if pipeline_graph_formats:
                                    saved_graph_sections.append(("pipeline", pipeline_graph_formats))
                        except Exception as graph_exc:
                            typer.secho(f"⚠️  Warning: Could not generate built pipeline graph: {graph_exc}", fg=typer.colors.YELLOW)

                    # Print completion recap
                    end_time = time.time()
                    console = get_console()
                    console.print(f"\n[green]✓[/green] [bold]Pipeline built successfully ({end_time - start_time:.1f}s)[/bold]")
                    console.print(f"  Output saved to {extras_output_dir}:")
                    console.print(f"    [green]✓[/green] bundle.plx (domain: {domain_code}, main: {main_pipe_code})")
                    if saved_bundle_view_formats:
                        console.print(f"    [green]✓[/green] bundle_view: {', '.join(saved_bundle_view_formats)}")
                    if saved_structure_names:
                        console.print(f"    [green]✓[/green] structures: {', '.join(saved_structure_names)}")
                    if has_inputs:
                        console.print(f"    [green]✓[/green] {DEFAULT_INPUTS_FILE_NAME}")
                    console.print(f"    [green]✓[/green] run_{main_pipe_code}.py")
                    for graph_label, graph_formats in saved_graph_sections:
                        console.print(f"    [green]✓[/green] graphs/{graph_label}: {', '.join(graph_formats)}")
                    if has_inputs:
                        console.print(f"\n  [yellow]Note:[/yellow] Fill {DEFAULT_INPUTS_FILE_NAME} with actual data before running.")
                        console.print(f"  To run: [cyan]pipelex run {extras_output_dir}[/cyan]")
                    else:
                        console.print(f"\n  To run: [cyan]pipelex run {extras_output_dir}[/cyan]")

                except Exception as exc:
                    typer.secho(f"⚠️  Warning: Could not generate extras: {exc}", fg=typer.colors.YELLOW)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_PIPE}")

            asyncio.run(run_pipeline())

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        Pipelex.teardown_if_needed()
