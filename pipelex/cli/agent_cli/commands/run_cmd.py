"""Agent CLI run command - simplified pipeline execution with JSON output."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME, DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner
from pipelex.tools.misc.json_utils import JsonTypeError, clean_json_dumps, load_json_dict_from_path


async def _run_pipeline_core(
    pipe_code: str,
    mthds_content: str | None = None,
    bundle_uri: str | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
    mock_inputs: bool = False,
    library_dirs: list[str] | None = None,
    graph: bool = False,
) -> dict[str, Any]:
    """Core logic for running a pipeline and returning JSON-serializable output.

    Args:
        pipe_code: The pipe code to run.
        mthds_content: MTHDS content string (optional).
        bundle_uri: Bundle file path (optional).
        inputs: Input dictionary for the pipeline.
        dry_run: Whether to run in dry mode (no actual inference).
        mock_inputs: Whether to generate mock data for missing inputs.
        library_dirs: List of library directories to search for pipe definitions.
        graph: Whether to generate execution graph visualizations.

    Returns:
        Dictionary with execution results suitable for JSON serialization.

    Raises:
        PipelineExecutionError: If the pipeline execution fails.
    """
    pipe_run_mode = PipeRunMode.DRY if dry_run else None

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=graph,
        mock_inputs=mock_inputs or None,
    )

    runner = PipelexRunner(
        bundle_uri=bundle_uri,
        pipe_run_mode=pipe_run_mode,
        execution_config=execution_config,
        library_dirs=library_dirs,
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_content=mthds_content,
        inputs=inputs,
    )
    pipe_output = response.pipe_output

    main_stuff = pipe_output.working_memory.get_optional_main_stuff()
    main_stuff_json: dict[str, Any] = {}
    if main_stuff:
        main_stuff_json = {
            "json": await main_stuff.content.rendered_json_async(),
            "markdown": await main_stuff.content.rendered_markdown_async(),
            "html": await main_stuff.content.rendered_html_async(),
        }

    result: dict[str, Any] = {
        "success": True,
        "pipe_code": pipe_code,
        "dry_run": dry_run,
        "main_stuff": main_stuff_json,
        "working_memory": pipe_output.working_memory.smart_dump(),
    }

    # Determine output directory: next to the bundle, or pipelex-wip/ fallback
    output_dir: Path
    if bundle_uri:
        output_dir = Path(bundle_uri).parent
    else:
        output_dir = Path("pipelex-wip")

    # Save output JSON next to the bundle (mirrors graph naming: dry_run.html / live_run.html)
    output_filename = "dry_run.json" if dry_run else "live_run.json"
    output_path = output_dir / output_filename
    output_path.write_text(clean_json_dumps(result, indent=2), encoding="utf-8")
    result["output_file"] = str(output_path)

    # Generate and save graph visualizations if requested
    if graph and pipe_output.graph_spec:
        graph_config = execution_config.graph_config
        # Enable ReactFlow HTML output and data inclusion for the render
        render_graph_config = graph_config.model_copy(
            update={
                "data_inclusion": graph_config.data_inclusion.model_copy(
                    update={
                        "stuff_json_content": True,
                        "stuff_text_content": True,
                        "stuff_html_content": True,
                    }
                ),
                "graphs_inclusion": graph_config.graphs_inclusion.model_copy(
                    update={
                        "graphspec_json": False,
                        "mermaidflow_html": False,
                        "reactflow_html": True,
                    }
                ),
            }
        )

        graph_outputs = await generate_graph_outputs(
            graph_spec=pipe_output.graph_spec,
            graph_config=render_graph_config,
            pipe_code=pipe_code,
        )

        saved_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)

        # Rename reactflow.html to mode-aware filename
        graph_filename = "dry_run.html" if dry_run else "live_run.html"
        reactflow_path = saved_files.get("reactflow_html")
        if reactflow_path:
            final_path = reactflow_path.parent / graph_filename
            reactflow_path.rename(final_path)
            result["graph_files"] = {"graph_html": str(final_path)}

    return result


def run_cmd(
    ctx: typer.Context,
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.mthds)"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Path to JSON file with inputs or inline JSON"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    graph: Annotated[
        bool,
        typer.Option("--graph/--no-graph", help="Generate execution graph visualizations (saved alongside output)"),
    ] = True,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Execute a pipeline and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.
    Graph visualizations are generated by default; use --no-graph to disable.

    Examples:
        pipelex-agent run pipelex-wip/pipeline_01/
        pipelex-agent run my_bundle.mthds --pipe my_pipe
        pipelex-agent run my_pipe --dry-run --mock-inputs
        pipelex-agent run pipelex-wip/pipeline_01/ --no-graph
    """
    # Validate that at least one target is provided
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        agent_error("--mock-inputs requires --dry-run", "ArgumentError")

    # Determine pipe_code and bundle_path from arguments
    pipe_code: str | None = None
    bundle_path: str | None = None

    if target:
        target_path = Path(target)
        if target_path.is_dir():
            # Directory mode: auto-detect bundle, inputs, and library dir
            if bundle:
                agent_error("Cannot use --bundle when passing a pipeline directory as target", "ArgumentError")

            # Find .mthds: try default name first, then fall back to single .mthds
            bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
            if bundle_file.is_file():
                bundle_path = str(bundle_file)
            else:
                mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
                if len(mthds_files) == 0:
                    agent_error(f"No .mthds bundle file found in directory '{target}'", "FileNotFoundError")
                if len(mthds_files) > 1:
                    mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                    agent_error(
                        f"Multiple .mthds files found in '{target}' ({mthds_names}) and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                        f"Pass the .mthds file directly instead.",
                        "ArgumentError",
                    )
                bundle_path = str(mthds_files[0])

            # Auto-detect inputs if --inputs not explicitly provided
            inputs_file = target_path / DEFAULT_INPUTS_FILE_NAME
            if not inputs and inputs_file.is_file():
                inputs = str(inputs_file)

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

        elif is_pipelex_file(target_path):
            bundle_path = target
            if bundle:
                agent_error("Cannot use --bundle if already passing a bundle file as positional argument", "ArgumentError")
        else:
            pipe_code = target
            if pipe:
                agent_error("Cannot use --pipe if already passing a pipe code as positional argument", "ArgumentError")

    if bundle:
        bundle_path = bundle

    if pipe:
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    # Load MTHDS content from bundle if provided
    mthds_content: str | None = None
    if bundle_path:
        try:
            mthds_content = Path(bundle_path).read_text(encoding="utf-8")
            if not pipe_code:
                bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
                main_pipe_code = bundle_blueprint.main_pipe
                if not main_pipe_code:
                    agent_error(
                        f"Bundle '{bundle_path}' does not declare a main_pipe. Specify a pipe code with --pipe.",
                        "BundleError",
                    )
                pipe_code = main_pipe_code
        except FileNotFoundError as exc:
            agent_error(f"Bundle file not found: {bundle_path}", "FileNotFoundError", cause=exc)
        except (OSError, UnicodeDecodeError) as exc:
            agent_error(f"Failed to read bundle file '{bundle_path}': {exc}", type(exc).__name__, cause=exc)
        except (PipelexInterpreterError, MthdsDecodeError) as exc:
            agent_error(f"Failed to parse bundle '{bundle_path}': {exc}", type(exc).__name__, cause=exc)

    # Load inputs if provided
    pipeline_inputs: dict[str, Any] | None = None
    if inputs:
        if inputs.startswith("{"):
            try:
                pipeline_inputs = json.loads(inputs)
            except json.JSONDecodeError as exc:
                agent_error(f"Failed to parse inline JSON inputs: {exc}", "JSONDecodeError", cause=exc)
        else:
            try:
                pipeline_inputs = load_json_dict_from_path(inputs)
            except FileNotFoundError as exc:
                agent_error(f"Input file not found: {inputs}", "FileNotFoundError", cause=exc)
            except JsonTypeError as exc:
                agent_error(f"Input file must be a valid JSON dictionary: {inputs}", "JsonTypeError", cause=exc)

    make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"])

    try:
        result = asyncio.run(
            _run_pipeline_core(
                pipe_code=pipe_code,  # type: ignore[arg-type]
                mthds_content=mthds_content,
                bundle_uri=bundle_path,
                inputs=pipeline_inputs,
                dry_run=dry_run,
                mock_inputs=mock_inputs,
                library_dirs=library_dir,
                graph=graph,
            )
        )
        agent_success(result)

    except PipelineExecutionError as exc:
        extra_fields: dict[str, Any] = {
            "pipe_code": exc.pipe_code,
            "pipe_stack": exc.pipe_stack,
        }
        if exc.__cause__:
            extra_fields["cause_type"] = type(exc.__cause__).__name__
            extra_fields["cause_message"] = str(exc.__cause__)
        agent_error(exc.message, "PipelineExecutionError", cause=exc, **extra_fields)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            "PipeOperatorModelChoiceError",
            cause=exc,
            pipe_code=exc.pipe_code,
            model_type=str(exc.model_type),
            model_choice=str(exc.model_choice),
        )

    except PipeOperatorModelAvailabilityError as exc:
        availability_extra: dict[str, Any] = {
            "pipe_code": exc.pipe_code,
            "model_handle": exc.model_handle,
        }
        if exc.fallback_list:
            availability_extra["fallback_list"] = exc.fallback_list
        if exc.pipe_stack:
            availability_extra["pipe_stack"] = exc.pipe_stack
        agent_error(exc.message, "PipeOperatorModelAvailabilityError", cause=exc, **availability_extra)

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
