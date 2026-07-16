"""Agent CLI validate bundle command - validate a bundle file or directory with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_error_validate_bundle,
    agent_success_formatted,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,
    validate_pipe_in_bundle_core,
)
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, generate_graph_for_bundle, generate_view_for_bundle
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError, ValidateBundleError
from pipelex.pipeline.validation_render import format_validate_markdown
from pipelex.tools.misc.chart_utils import FlowchartDirection


def validate_bundle_cmd(
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
        typer.Option("--graph-format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
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
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Validate a bundle file (.mthds) or pipeline directory and output the results.

    Default output is markdown; use --format json for structured JSON.
    Results go to stdout on success, errors to stderr with exit code 1.

    Examples:
        pipelex-agent validate bundle my_bundle.mthds
        pipelex-agent validate bundle my_bundle.mthds --pipe my_pipe
        pipelex-agent validate bundle my_bundle.mthds --graph
        pipelex-agent validate bundle pipeline_01/
        pipelex-agent validate bundle pipeline_01/ --graph
        pipelex-agent validate bundle draft_pipeline.mthds --allow-signatures
    """
    set_agent_cli_error_format(error_format or output_format)

    bundle_path, library_dir = resolve_bundle_target(path, library_dir=library_dir)

    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Convert library_dirs to list[str] for graph helper
    library_dir_strings = [str(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False, needs_model_specs=True)

    try:
        if pipe:
            # Validate a specific pipe within the bundle
            result = asyncio.run(
                validate_pipe_in_bundle_core(
                    bundle_path=Path(bundle_path), pipe_code=pipe, library_dirs=library_dirs, allow_signatures=allow_signatures
                )
            )
        else:
            # Validate the entire bundle
            result = asyncio.run(validate_bundle_core(bundle_path=Path(bundle_path), library_dirs=library_dirs, allow_signatures=allow_signatures))

        # Generate graph if requested and validation succeeded
        if graph:
            try:
                graph_result = asyncio.run(
                    generate_graph_for_bundle(
                        bundle_path=Path(bundle_path),
                        graph_format=graph_format,
                        library_dirs=library_dir_strings,
                        pipe_code=pipe,
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
                agent_error(f"Graph generation failed: {exc.message}", error_type="PipelineExecutionError", cause=exc, exit_code=2, **graph_extra)
            except PipelexInterpreterError as exc:
                agent_error(f"Graph generation failed: {exc}", error_type=type(exc).__name__, cause=exc, exit_code=2)
            except typer.Exit:
                raise
            except Exception as exc:  # noqa: BLE001
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
                agent_error(f"Graph generation failed: {exc}", error_type=type(exc).__name__, cause=exc, exit_code=2)

        # Generate view (GraphSpec JSON) if requested and validation succeeded
        if view:
            try:
                view_result = asyncio.run(
                    generate_view_for_bundle(
                        bundle_path=Path(bundle_path),
                        library_dirs=library_dir_strings,
                        pipe_code=pipe,
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
                agent_error(f"View generation failed: {exc.message}", error_type="PipelineExecutionError", cause=exc, exit_code=2, **view_extra)
            except PipelexInterpreterError as exc:
                agent_error(f"View generation failed: {exc}", error_type=type(exc).__name__, cause=exc, exit_code=2)
            except typer.Exit:
                raise
            except Exception as exc:  # noqa: BLE001
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
                agent_error(f"View generation failed: {exc}", error_type=type(exc).__name__, cause=exc, exit_code=2)

        agent_success_formatted(result, markdown_renderer=format_validate_markdown, output_format=output_format)

        # Gate-from-report (D-B consumer-decides): the bundle is valid, but unsatisfied PipeSignature
        # placeholders make it NOT runnable. The success envelope (carrying pending_signatures +
        # is_runnable) is already emitted above; the exit code — not a fabricated error item — reflects
        # the gate. --allow-signatures tolerates the placeholders (exit 0). Re-raised by the
        # `except typer.Exit` arm below so teardown still runs.
        #
        # Only the whole-bundle path gates: with --pipe, `result` is the slice envelope whose
        # is_runnable derives from LIBRARY-WIDE pending_signatures, so gating there would fail a
        # fully-implemented slice for unrelated placeholders elsewhere in the bundle. The slice makes
        # no library-wide runnability claim (mirroring `validate pipe`), so it is not gated.
        if not pipe and not allow_signatures and not result.get("is_runnable", True):
            raise typer.Exit(1)

    except PipeNotFoundError as exc:
        agent_error(str(exc), error_type="PipeNotFoundError", cause=exc, exit_code=2)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", error_type="FileNotFoundError", cause=exc, exit_code=2)

    except ValidateBundleError as exc:
        # Invalid verdict: emit the format-aware failure surface. JSON keeps the exact structured
        # envelope (is_valid:false discriminant + validation_errors[], the shared builder's output,
        # non-empty on every invalid verdict); markdown renders those items as prose with a fix-aware
        # footer. Signatures never reach here (they are a runnability fact, gated above).
        agent_error_validate_bundle(exc, bundle_path=Path(bundle_path), library_dirs=library_dirs, allow_signatures=allow_signatures)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            error_type="PipeOperatorModelChoiceError",
            cause=exc,
            exit_code=2,
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
        agent_error(exc.message, error_type="PipeOperatorModelAvailabilityError", cause=exc, exit_code=2, **availability_extra)

    except typer.Exit:
        raise

    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc, exit_code=2)

    finally:
        Pipelex.teardown_if_needed()
