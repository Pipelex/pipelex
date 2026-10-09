"""Agent CLI run method command - execute a pipeline for an installed method."""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    run_failure_fields,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.run._output_helpers import format_run_markdown
from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core
from pipelex.cli.agent_cli.commands.run._run_hosted import (
    BASE_URL_OPTION_HELP,
    HOSTED_OPTION_HELP,
    RUNNER_OPTION_HELP,
    refuse_local_only_flags,
    resolve_agent_run_execution,
    run_hosted_for_agent,
)
from pipelex.cli.agent_cli.commands.run.stdin_resolver import parse_cli_inputs
from pipelex.cli.commands.run._hosted_sources import resolve_hosted_method_target
from pipelex.cli.commands.run._inputs_file_loader import resolve_inputs_arg_against_dir
from pipelex.cli.method_resolver import method_output_base_dir, resolve_method_target
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.hosted.hosted_run import HostedRunRequest
from pipelex.hosted.run_config import RunExecution  # ruff: ignore[typing-only-first-party-import] - typer reads the --runner annotation at runtime
from pipelex.methods.exceptions import MethodRefError
from pipelex.mthds_parsing.helpers import MTHDS_EXTENSION
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError


def run_method_cmd(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "Installed method name, local method directory, method address (github.com/owner/repo\\[/name]\\[@tag]), "
                "GitHub URL, or, on a hosted run, a catalog id (mt_…)"
            ),
        ),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Inputs: a JSON or TOML file (by its extension), or inline JSON starting with {"),
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
    costs: Annotated[
        bool,
        typer.Option("--costs/--no-costs", help="Emit usage (cost) tracing events. Default on."),
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
    runner: Annotated[
        RunExecution | None,
        typer.Option("--runner", help=RUNNER_OPTION_HELP),
    ] = None,
    hosted: Annotated[
        bool | None,
        typer.Option("--hosted/--local", help=HOSTED_OPTION_HELP),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help=BASE_URL_OPTION_HELP),
    ] = None,
) -> None:
    """Execute a pipeline for an installed method and output the results.

    Resolves the method by name, determines the pipe code from the method's main_pipe
    (or --pipe override), and runs the pipeline. Default output is markdown;
    use --format json for structured JSON.

    With --runner hosted (or [run] execution = "hosted"), the run executes on the hosted
    Pipelex API: an address or a catalog id (mt_...) is resolved there, an installed or
    local method's files are sent, and local files named in the inputs are uploaded.

    Examples:
        pipelex-agent run method my-method
        pipelex-agent run method my-method --pipe custom_pipe
        pipelex-agent run method my-method --dry-run --mock-inputs
        pipelex-agent run method github.com/Pipelex/methods/text_stats@v0.1.7 --runner hosted --inputs '{"text": "Hello"}'
    """
    set_agent_cli_error_format(error_format or output_format)

    # Validate --mock-inputs requires --dry-run
    if mock_inputs and not dry_run:
        agent_error("--mock-inputs requires --dry-run", error_type="ArgumentError")

    execution = resolve_agent_run_execution(runner=runner, hosted=hosted, base_url=base_url)
    if execution.is_hosted:
        refuse_local_only_flags(dry_run=dry_run, mock_inputs=mock_inputs)
        # A published address and a stored method are resolved by the hosted API, so nothing is fetched here; an
        # installed or local method is resolved as on a local run, and its files are sent.
        try:
            target = resolve_hosted_method_target(name=name, pipe_override=pipe, library_dirs=library_dir)
        except (HostedRunSourceError, MethodRefError) as exc:
            agent_error(exc.message, error_type=type(exc).__name__, cause=exc)
        hosted_inputs = parse_cli_inputs(
            inputs_arg=resolve_inputs_arg_against_dir(inputs, base_dir=target.inputs_anchor_dir),
            stdin_fallback=True,
        )
        request = HostedRunRequest(
            mthds_files=target.mthds_files,
            method_ref=target.method_ref,
            method_id=target.method_id,
            pipe_code=target.pipe_code,
            inputs=hosted_inputs.pipeline_inputs,
            inputs_base_dir=hosted_inputs.inputs_base_dir,
        )
        run_hosted_for_agent(request=request, base_url=base_url, with_memory=with_memory, output_format=output_format)
        return

    try:
        pipe_code, method_library_dirs, method = resolve_method_target(
            method_name=name,
            pipe_override=pipe,
            library_dirs=library_dir,
            raise_ref_errors=True,
        )
    except MethodRefError as exc:
        # Method-reference failure (parse, fetch, location, bounds, refusal): report it through
        # the structured error envelope instead of the human CLI's plain red text.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    # A fetched method's package directory is an ephemeral clone deleted at process exit —
    # anchor run outputs (output JSON, graph files) in a durable location instead.
    output_dir_override: Path | None = None
    if method.provenance is not None:
        output_dir_override = method_output_base_dir(method=method) / "results"

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

    # Resolve a relative --inputs file path against the method's directory (same rule as the main CLI)
    effective_inputs = resolve_inputs_arg_against_dir(inputs, base_dir=Path(method_library_dirs[0]))

    # Load inputs: --inputs flag takes priority, then stdin fallback
    parsed_inputs = parse_cli_inputs(inputs_arg=effective_inputs, stdin_fallback=True)
    pipeline_inputs: dict[str, Any] | None = parsed_inputs.pipeline_inputs

    make_pipelex_for_agent_cli(needs_inference=not dry_run)

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
                costs=costs,
                with_memory=with_memory,
                inputs_base_dir=parsed_inputs.inputs_base_dir,
                output_dir_override=output_dir_override,
            )
        )
        agent_success_formatted(
            result, markdown_renderer=functools.partial(format_run_markdown, with_memory=with_memory), output_format=output_format
        )

    except PipelineExecutionError as exc:
        agent_error(exc.message, error_type="PipelineExecutionError", cause=exc, **run_failure_fields(error=exc))

    except PipeOperatorModelAvailabilityError as exc:
        availability_extra: dict[str, Any] = {
            "pipe_code": exc.pipe_code,
            "model_handle": exc.model_handle,
        }
        if exc.fallback_list:
            availability_extra["fallback_list"] = exc.fallback_list
        if exc.pipe_stack:
            availability_extra["pipe_stack"] = exc.pipe_stack
        agent_error(exc.message, error_type="PipeOperatorModelAvailabilityError", cause=exc, **availability_extra)

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
