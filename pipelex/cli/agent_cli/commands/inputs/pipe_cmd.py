"""Agent CLI inputs pipe command - generate example inputs by pipe code."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import inputs_core
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError


def inputs_pipe_cmd(
    ctx: typer.Context,
    pipe_code: Annotated[
        str,
        typer.Argument(help="Pipe code to get inputs for"),
    ],
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe by code and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs pipe my_pipe
        pipelex-agent inputs pipe my_pipe -L ./my_pipes
    """
    # Helpful error if the user passes a path instead of a pipe code
    target_path = Path(pipe_code)
    if target_path.is_dir() or is_pipelex_file(target_path) or pipe_code.endswith(MTHDS_EXTENSION):
        agent_error(
            f"'{pipe_code}' looks like a file path or directory. "
            f"Use 'inputs bundle {pipe_code}' for bundles/directories, or 'inputs pipe <code>' for pipe codes.",
            "ArgumentError",
        )

    # Check installed methods' exports for additional library dirs
    try:
        export_dirs = resolve_pipe_from_exports(pipe_code)
    except ValueError as exc:
        agent_error(
            f"Ambiguous pipe code '{pipe_code}': {exc}",
            "ArgumentError",
            cause=exc,
        )
    if export_dirs:
        if library_dir is None:
            library_dir = export_dirs
        else:
            library_dir = [*export_dirs, *library_dir]

    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
    make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(inputs_core(pipe_code=pipe_code, bundle_path=None, library_dirs=library_dirs))
        agent_success(result)

    except FileNotFoundError as exc:
        agent_error(f"File not found: {exc}", "FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            extra["dry_run_error"] = exc.dry_run_error_message
        agent_error(exc.message, "ValidateBundleError", cause=exc, **extra)

    except NoInputsRequiredError as exc:
        # Not really an error - just a pipe with no inputs
        agent_success(
            {
                "success": True,
                "pipe_code": pipe_code,
                "inputs": {},
                "message": str(exc),
            }
        )

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

    except Exception as exc:  # noqa: BLE001
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
