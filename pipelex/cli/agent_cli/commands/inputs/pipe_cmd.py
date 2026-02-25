"""Agent CLI inputs pipe command - generate example inputs by pipe code or bundle path."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import inputs_core
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError


def inputs_pipe_cmd(
    ctx: typer.Context,
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to get inputs for"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs pipe my_pipe
        pipelex-agent inputs pipe my_bundle.mthds
        pipelex-agent inputs pipe my_bundle.mthds --pipe my_pipe
        pipelex-agent inputs pipe my_pipe -L ./my_pipes
    """
    # Validate that at least one target is provided
    if target is None and pipe is None:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    # Determine pipe_code and bundle_path from arguments
    pipe_code: str | None = None
    bundle_path: Path | None = None

    if target:
        target_path = Path(target)
        if target_path.is_dir():
            agent_error(
                f"'{target}' is a directory. The inputs command requires a .mthds file or a pipe code.",
                "ArgumentError",
            )

        if is_pipelex_file(target_path):
            bundle_path = target_path
        else:
            pipe_code = target
            if pipe:
                agent_error("Cannot use --pipe if already passing a pipe code as positional argument", "ArgumentError")

    if pipe:
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
    make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"])

    try:
        result = asyncio.run(inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, library_dirs=library_dirs))
        agent_success(result)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", "FileNotFoundError", cause=exc)

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

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
