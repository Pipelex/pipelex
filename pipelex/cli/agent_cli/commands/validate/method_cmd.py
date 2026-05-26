"""Agent CLI validate method command - validate an installed method."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    extract_validation_errors,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.validate._output_helpers import format_validate_markdown
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,
    validate_pipe_in_bundle_core,
)
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError


def validate_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (overrides method's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Validate an installed method and output the results.

    Resolves the method by name, finds its .mthds bundle, and validates it.
    If --pipe is provided, validates only that specific pipe within the bundle.
    Default output is markdown; use --format json for structured JSON.

    Examples:
        pipelex-agent validate method my-method
        pipelex-agent validate method my-method --pipe custom_pipe
    """
    set_agent_cli_error_format(error_format or output_format)

    pipe_code, method_library_dirs, method = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )
    if not method.mthds_files:
        agent_error(f"Method '{name}' has no .mthds bundle files.", "MethodError")

    bundle_path = method.mthds_files[0]

    # Merge library dirs: method dirs first, then user-specified
    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dir:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dir)

    make_pipelex_for_agent_cli(library_dirs=library_dirs_paths, needs_inference=False, needs_model_specs=True)

    try:
        if pipe:
            # Validate a specific pipe within the method's bundle
            result = asyncio.run(validate_pipe_in_bundle_core(bundle_path=bundle_path, pipe_code=pipe_code, library_dirs=library_dirs_paths))
        else:
            # Validate the entire bundle
            result = asyncio.run(validate_bundle_core(bundle_path=bundle_path, library_dirs=library_dirs_paths))

        agent_success_formatted(result, format_validate_markdown, output_format)

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

    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
