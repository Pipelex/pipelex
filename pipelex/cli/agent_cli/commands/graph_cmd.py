"""Agent CLI graph command - generate graph HTML from a .mthds bundle via dry-run."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, render_graph_from_spec
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner
from pipelex.tools.misc.chart_utils import FlowchartDirection


def graph_cmd(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file"),
    ],
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.REACTFLOW,
    direction: Annotated[
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Generate graph visualization from a .mthds bundle.

    Performs a dry-run of the pipeline with mock inputs to produce the execution
    graph, then renders it as HTML.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent graph bundle.mthds
        pipelex-agent graph bundle.mthds --format mermaidflow
        pipelex-agent graph bundle.mthds --direction left_to_right
        pipelex-agent graph bundle.mthds -L ./my_pipes/
    """
    input_path = Path(target)

    if not input_path.exists():
        agent_error(f"File not found: {target}", "FileNotFoundError")

    if not is_pipelex_file(input_path):
        agent_error(f"Expected a .mthds bundle file, got: {input_path.name}", "ArgumentError")

    # Read MTHDS content and extract main pipe
    try:
        mthds_content = input_path.read_text(encoding="utf-8")
        bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        main_pipe_code = bundle_blueprint.main_pipe
        if not main_pipe_code:
            agent_error(
                f"Bundle '{target}' does not declare a main_pipe.",
                "BundleError",
            )
        pipe_code: str = main_pipe_code
    except (OSError, UnicodeDecodeError) as exc:
        agent_error(f"Failed to read bundle file '{target}': {exc}", type(exc).__name__, cause=exc)
    except (PipelexInterpreterError, MthdsDecodeError) as exc:
        agent_error(f"Failed to parse bundle '{target}': {exc}", type(exc).__name__, cause=exc)

    # Initialize Pipelex
    make_pipelex_for_agent_cli(library_dirs=library_dir, log_level=ctx.obj["log_level"])

    try:
        # Configure execution for dry-run with graph generation
        execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
            generate_graph=True,
            mock_inputs=True,
        )

        runner = PipelexRunner(
            bundle_uri=target,
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=execution_config,
            library_dirs=library_dir,
        )
        response = asyncio.run(
            runner.execute_pipeline(
                pipe_code=pipe_code,
                mthds_content=mthds_content,
            )
        )
        pipe_output = response.pipe_output

        if not pipe_output.graph_spec:
            agent_error("Pipeline execution did not produce a graph spec", "GraphSpecMissingError")

        graph_spec = pipe_output.graph_spec

        # Render and save graph files alongside the bundle
        output_dir = input_path.parent
        include_mermaidflow: bool
        include_reactflow: bool
        match graph_format:
            case GraphFormat.MERMAIDFLOW:
                include_mermaidflow = True
                include_reactflow = False
            case GraphFormat.REACTFLOW:
                include_mermaidflow = False
                include_reactflow = True
            case GraphFormat.BOTH:
                include_mermaidflow = True
                include_reactflow = True

        saved_files = asyncio.run(
            render_graph_from_spec(
                graph_spec=graph_spec,
                graph_config=execution_config.graph_config,
                include_mermaidflow=include_mermaidflow,
                include_reactflow=include_reactflow,
                output_dir=output_dir,
                pipe_code=pipe_code,
                direction=direction,
            )
        )

        agent_success(
            {
                "success": True,
                "output_dir": str(output_dir),
                "files": {key: str(path) for key, path in saved_files.items()},
                "pipe_code": pipe_code,
                "direction": str(direction) if direction else None,
            }
        )

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

    except typer.Exit:
        raise

    except Exception as exc:
        agent_error(f"Failed to generate graph: {exc}", type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
