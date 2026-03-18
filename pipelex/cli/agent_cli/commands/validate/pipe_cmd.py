"""Agent CLI validate pipe command - validate a pipe by code or all pipes with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_all_core,
    validate_pipe_core,
)
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError


def validate_pipe_cmd(
    ctx: typer.Context,
    pipe_code: Annotated[
        str | None,
        typer.Argument(help="Pipe code to validate"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Validate a pipe by code, or all pipes, and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent validate pipe my_pipe
        pipelex-agent validate pipe --all
        pipelex-agent validate pipe --all -L ./my_pipes
    """
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Handle --all flag
    if validate_all:
        if pipe_code:
            agent_error("--all cannot be used with a pipe code", "ArgumentError")

        make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

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

    if not pipe_code:
        agent_error(
            "No pipe code specified. Use --all to validate all pipes, or use 'validate bundle <path>' for bundle files.",
            "ArgumentError",
        )

    # Helpful error if the user passes a path instead of a pipe code
    target_path = Path(pipe_code)
    if target_path.is_dir() or is_pipelex_file(target_path) or pipe_code.endswith(MTHDS_EXTENSION):
        agent_error(
            f"'{pipe_code}' looks like a file path or directory. "
            f"Use 'validate bundle {pipe_code}' for bundles/directories, or 'validate pipe <code>' for pipe codes.",
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
        export_paths = [Path(export_dir) for export_dir in export_dirs]
        if library_dirs is None:
            library_dirs = export_paths
        else:
            library_dirs = [*export_paths, *library_dirs]

    make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(validate_pipe_core(pipe_code=pipe_code, library_dirs=library_dirs))
        agent_success(result)

    except PipeNotFoundError as exc:
        error_message = str(exc)
        if pipe_code == "all":
            error_message += " Did you mean '--all'?"
        agent_error(error_message, "PipeNotFoundError", cause=exc)

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
