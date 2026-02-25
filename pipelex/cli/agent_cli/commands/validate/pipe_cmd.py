"""Agent CLI validate pipe command - validate pipes/bundles with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_all_core,
    validate_bundle_core,
    validate_pipe_core,
    validate_pipe_in_bundle_core,
)
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, generate_graph_for_bundle
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.validate_bundle import ValidateBundleError
from pipelex.tools.misc.chart_utils import FlowchartDirection


def validate_pipe_cmd(
    ctx: typer.Context,
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.mthds)"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
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
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Validate a pipe, bundle, or all pipes and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent validate pipe my_pipe
        pipelex-agent validate pipe my_bundle.mthds
        pipelex-agent validate pipe my_bundle.mthds --graph
        pipelex-agent validate pipe --all -L ./my_pipes
    """
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
    # Handle --all flag
    if validate_all:
        if graph:
            agent_error("--graph requires a bundle target; it cannot be used with --all", "ArgumentError")
        if target or pipe or bundle:
            agent_error("--all cannot be used with a target, --pipe, or --bundle", "ArgumentError")

        make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"])

        try:
            result = asyncio.run(validate_all_core(library_dirs=library_dirs))
            agent_success(result)

        except ValidateBundleError as exc:
            validation_errors = extract_validation_errors(exc)
            validate_all_extra: dict[str, Any] = {"validation_errors": validation_errors}
            if exc.dry_run_error_message:
                validate_all_extra["dry_run_error"] = exc.dry_run_error_message
            agent_error(exc.message, "ValidateBundleError", cause=exc, **validate_all_extra)

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
            agent_error(
                str(exc),
                "PipeOperatorModelAvailabilityError",
                cause=exc,
                pipe_code=exc.pipe_code,
                model_handle=exc.model_handle,
            )

        except Exception as exc:
            agent_error(str(exc), type(exc).__name__, cause=exc)

        finally:
            Pipelex.teardown_if_needed()
        return

    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        agent_error("No pipe code or bundle file specified. Use --all to validate all pipes.", "ArgumentError")

    # Determine pipe_code and bundle_path from arguments
    pipe_code: str | None = None
    bundle_path: Path | None = None

    if target:
        target_path = Path(target)
        if is_pipelex_file(target_path):
            bundle_path = target_path
            if bundle:
                agent_error("Cannot use --bundle if already passing a bundle file as positional argument", "ArgumentError")
        else:
            pipe_code = target
            if pipe:
                agent_error("Cannot use --pipe if already passing a pipe code as positional argument", "ArgumentError")

    if bundle:
        bundle_path = Path(bundle)

    if pipe:
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    # --graph requires a bundle
    if graph and not bundle_path:
        agent_error("--graph requires a bundle target; it cannot be used with a standalone pipe", "ArgumentError")

    # Convert library_dirs to list[str] for graph helper (PipelexRunner expects list[str])
    library_dir_strings = [str(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"])

    try:
        if bundle_path and pipe_code:
            # Validate a specific pipe within a bundle
            result = asyncio.run(validate_pipe_in_bundle_core(bundle_path=bundle_path, pipe_code=pipe_code, library_dirs=library_dirs))
        elif bundle_path:
            # Validate the entire bundle
            result = asyncio.run(validate_bundle_core(bundle_path=bundle_path, library_dirs=library_dirs))
        else:
            # Validate a standalone pipe
            result = asyncio.run(validate_pipe_core(pipe_code=pipe_code, library_dirs=library_dirs))  # type: ignore[arg-type]

        # Generate graph if requested and validation succeeded with a bundle
        if graph and bundle_path:
            try:
                graph_result = asyncio.run(
                    generate_graph_for_bundle(
                        bundle_path=bundle_path,
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

        agent_success(result)

    except PipeNotFoundError as exc:
        error_message = str(exc)
        if pipe_code == "all":
            error_message += " Did you mean '--all'?"
        agent_error(error_message, "PipeNotFoundError", cause=exc)

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
