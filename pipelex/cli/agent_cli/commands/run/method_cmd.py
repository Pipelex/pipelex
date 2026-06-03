"""Agent CLI run method command - execute a pipeline for an installed method."""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import Annotated, Any

import typer
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success_formatted, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.run._output_helpers import format_run_markdown
from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core
from pipelex.cli.agent_cli.commands.run._run_core_api import run_pipeline_core_api
from pipelex.cli.agent_cli.commands.run.stdin_resolver import parse_cli_inputs
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError


def run_method_cmd(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
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
    with_memory: Annotated[
        bool,
        typer.Option("--with-memory", help="Include full working memory in output (for piping to another method)"),
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
    """Execute a pipeline for an installed method and output the results.

    Resolves the method by name, determines the pipe code from the method's main_pipe
    (or --pipe override), and runs the pipeline. Default output is markdown;
    use --format json for structured JSON.

    Examples:
        pipelex-agent run method my-method
        pipelex-agent run method my-method --pipe custom_pipe
        pipelex-agent run method my-method --dry-run --mock-inputs
    """
    set_agent_cli_error_format(error_format or output_format)

    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        agent_error("--mock-inputs requires --dry-run", "ArgumentError")

    pipe_code, method_library_dirs, method = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )
    bundle_path: str | None = None
    mthds_content: str | None = None

    if method.mthds_files:
        bundle_path = str(method.mthds_files[0])
        mthds_content = Path(bundle_path).read_text(encoding="utf-8")
    else:
        # Try to find .mthds files in the method directory
        mthds_files = list(method.path.glob(f"*{MTHDS_EXTENSION}"))
        if mthds_files:
            bundle_path = str(mthds_files[0])
            mthds_content = Path(bundle_path).read_text(encoding="utf-8")

    # Merge library dirs: method dirs first, then user-specified
    all_library_dirs = list(method_library_dirs)
    if library_dir:
        all_library_dirs.extend(library_dir)

    # Load inputs: --inputs flag takes priority, then stdin fallback
    pipeline_inputs: dict[str, Any] | None = parse_cli_inputs(inputs_arg=inputs, stdin_fallback=True)

    runner_type: RunnerType = ctx.obj["runner"]

    match runner_type:
        case RunnerType.API:
            # Validate unsupported flags for API runner
            if dry_run:
                agent_error("--dry-run is not supported with --runner api", "ArgumentError")
            if mock_inputs:
                agent_error("--mock-inputs is not supported with --runner api", "ArgumentError")

            from mthds.client.exceptions import ClientAuthenticationError, PipelineRequestError  # noqa: PLC0415

            try:
                result = asyncio.run(
                    run_pipeline_core_api(
                        pipe_code=pipe_code,
                        mthds_contents=[mthds_content] if mthds_content else None,
                        inputs=pipeline_inputs,
                        with_memory=with_memory,
                    )
                )
                agent_success_formatted(result, functools.partial(format_run_markdown, with_memory=with_memory), output_format)

            except ClientAuthenticationError as exc:
                agent_error(str(exc), "ClientAuthenticationError", cause=exc)

            except PipelineRequestError as exc:
                agent_error(str(exc), "PipelineRequestError", cause=exc)

            except Exception as exc:  # noqa: BLE001
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
                agent_error(str(exc), type(exc).__name__, cause=exc)

        case RunnerType.PIPELEX:
            make_pipelex_for_agent_cli(needs_inference=not dry_run, needs_model_specs=True)

            try:
                result = asyncio.run(
                    run_pipeline_core(
                        pipe_code=pipe_code,
                        mthds_contents=[mthds_content] if mthds_content else None,
                        bundle_uris=[bundle_path] if bundle_path else None,
                        inputs=pipeline_inputs,
                        dry_run=dry_run,
                        mock_inputs=mock_inputs,
                        library_dirs=all_library_dirs,
                        graph=graph,
                        with_memory=with_memory,
                    )
                )
                agent_success_formatted(result, functools.partial(format_run_markdown, with_memory=with_memory), output_format)

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

            except Exception as exc:  # noqa: BLE001
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
                agent_error(str(exc), type(exc).__name__, cause=exc)

            finally:
                Pipelex.teardown_if_needed()
