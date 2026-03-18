"""Agent CLI validate bundle command - validate a bundle file or directory with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,
    validate_pipe_in_bundle_core,
)
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, generate_graph_for_bundle, generate_view_for_bundle
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.validate_bundle import ValidateBundleError
from pipelex.tools.misc.chart_utils import FlowchartDirection


def validate_bundle_cmd(
    ctx: typer.Context,
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (overrides bundle's main_pipe)"),
    ] = None,
    graph: Annotated[
        bool,
        typer.Option("--graph", "-g", help="On successful bundle validation, save graph HTML files and include their paths in the JSON output"),
    ] = False,
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.REACTFLOW,
    direction: Annotated[
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction"),
    ] = None,
    view: Annotated[
        bool,
        typer.Option("--view", help="On successful bundle validation, include a GraphSpec (structured JSON for graph rendering) in the output"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Validate a bundle file (.mthds) or pipeline directory and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent validate bundle my_bundle.mthds
        pipelex-agent validate bundle my_bundle.mthds --pipe my_pipe
        pipelex-agent validate bundle my_bundle.mthds --graph
        pipelex-agent validate bundle pipeline_01/
        pipelex-agent validate bundle pipeline_01/ --graph
    """
    bundle_path: str | None = None
    target_path = Path(path)

    if target_path.is_dir():
        # Directory mode: auto-detect bundle file
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                agent_error(f"No .mthds bundle file found in directory '{path}'", "FileNotFoundError")
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                agent_error(
                    f"Multiple .mthds files found in '{path}' ({mthds_names}) and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly instead.",
                    "ArgumentError",
                )
            bundle_path = str(mthds_files[0])

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

    elif is_pipelex_file(target_path):
        bundle_path = path
    else:
        agent_error(
            f"'{path}' is not a .mthds file or directory. "
            f"Use 'validate pipe <code>' for pipe codes, or 'validate bundle <path>' for .mthds files/directories.",
            "ArgumentError",
        )

    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Convert library_dirs to list[str] for graph helper
    library_dir_strings = [str(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

    try:
        if pipe:
            # Validate a specific pipe within the bundle
            result = asyncio.run(validate_pipe_in_bundle_core(bundle_path=Path(bundle_path), pipe_code=pipe, library_dirs=library_dirs))  # type: ignore[arg-type]
        else:
            # Validate the entire bundle
            result = asyncio.run(validate_bundle_core(bundle_path=Path(bundle_path), library_dirs=library_dirs))  # type: ignore[arg-type]

        # Generate graph if requested and validation succeeded
        if graph:
            try:
                graph_result = asyncio.run(
                    generate_graph_for_bundle(
                        bundle_path=Path(bundle_path),  # type: ignore[arg-type]
                        graph_format=graph_format,
                        library_dirs=library_dir_strings,
                        direction=direction,
                    )
                )
                result.update(graph_result)
            except PipelineExecutionError as exc:
                graph_extra: dict[str, Any] = {
                    "pipe_code": exc.pipe_code,
                    "pipe_stack": exc.pipe_stack,
                }
                if exc.__cause__:
                    graph_extra["cause_type"] = type(exc.__cause__).__name__
                    graph_extra["cause_message"] = str(exc.__cause__)
                agent_error(f"Graph generation failed: {exc.message}", "PipelineExecutionError", cause=exc, **graph_extra)
            except (PipelexInterpreterError, MthdsDecodeError) as exc:
                agent_error(f"Graph generation failed: {exc}", type(exc).__name__, cause=exc)
            except typer.Exit:
                raise
            except Exception as exc:
                agent_error(f"Graph generation failed: {exc}", type(exc).__name__, cause=exc)

        # Generate view (GraphSpec JSON) if requested and validation succeeded
        if view:
            try:
                view_result = asyncio.run(
                    generate_view_for_bundle(
                        bundle_path=Path(bundle_path),  # type: ignore[arg-type]
                        library_dirs=library_dir_strings,
                        direction=direction,
                    )
                )
                result.update(view_result)
            except PipelineExecutionError as exc:
                view_extra: dict[str, Any] = {
                    "pipe_code": exc.pipe_code,
                    "pipe_stack": exc.pipe_stack,
                }
                if exc.__cause__:
                    view_extra["cause_type"] = type(exc.__cause__).__name__
                    view_extra["cause_message"] = str(exc.__cause__)
                agent_error(f"View generation failed: {exc.message}", "PipelineExecutionError", cause=exc, **view_extra)
            except (PipelexInterpreterError, MthdsDecodeError) as exc:
                agent_error(f"View generation failed: {exc}", type(exc).__name__, cause=exc)
            except typer.Exit:
                raise
            except Exception as exc:
                agent_error(f"View generation failed: {exc}", type(exc).__name__, cause=exc)

        agent_success(result)

    except PipeNotFoundError as exc:
        agent_error(str(exc), "PipeNotFoundError", cause=exc)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", "FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            extra["dry_run_error"] = exc.dry_run_error_message
        agent_error(exc.message, "ValidateBundleError", cause=exc, **extra)

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
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
