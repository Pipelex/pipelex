"""Agent CLI graph command - generate graph HTML from a .mthds bundle via dry-run."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, generate_graph_for_bundle
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
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

    # Initialize Pipelex
    make_pipelex_for_agent_cli(library_dirs=library_dir, log_level=ctx.obj["log_level"])

    try:
        graph_result = asyncio.run(
            generate_graph_for_bundle(
                bundle_path=input_path,
                graph_format=graph_format,
                library_dirs=library_dir,
                direction=direction,
            )
        )

        agent_success(
            {
                "success": True,
                "output_dir": graph_result["graph_output_dir"],
                "files": graph_result["graph_files"],
                "pipe_code": graph_result["pipe_code"],
                "direction": graph_result["direction"],
            }
        )

    except (PipelexInterpreterError, MthdsDecodeError) as exc:
        agent_error(f"Failed to parse bundle '{target}': {exc}", type(exc).__name__, cause=exc)

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
