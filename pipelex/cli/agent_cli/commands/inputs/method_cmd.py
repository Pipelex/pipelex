"""Agent CLI inputs method command - generate example inputs for an installed method."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import inputs_core
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError


def inputs_method_cmd(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Generate example input JSON for an installed method and output JSON results.

    Resolves the method by name, finds its .mthds bundle, and generates inputs.

    Examples:
        pipelex-agent inputs method my-method
        pipelex-agent inputs method my-method --pipe custom_pipe
    """
    pipe_code, method_library_dirs, method = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )
    bundle_path: Path | None = None
    if method.mthds_files:
        bundle_path = method.mthds_files[0]

    # Merge library dirs: method dirs first, then user-specified
    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dir:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dir)

    make_pipelex_for_agent_cli(library_dirs=library_dirs_paths, log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, library_dirs=library_dirs_paths))
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
