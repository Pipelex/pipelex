"""Agent CLI validate command - simplified pipeline validation with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle


async def _validate_all_core(
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all pipes in all libraries.

    Args:
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    pipes = library.pipe_library.get_pipes()
    for the_pipe in pipes:
        the_pipe.validate_with_libraries()

    await dry_run_pipes(pipes=pipes, raise_on_failure=True)

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in pipes]

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(pipes),
    }


async def _validate_bundle_core(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a bundle file.

    Args:
        bundle_path: Path to the bundle file.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    result = await validate_bundle(plx_file_path=bundle_path, library_dirs=library_dirs)

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in result.pipes]

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
    }


async def _validate_pipe_core(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe.

    Args:
        pipe_code: The pipe code to validate.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, raise_on_failure=True)

    return {
        "success": True,
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


async def _validate_pipe_in_bundle_core(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    This first validates the bundle to load its pipes into the library,
    then validates only the specified pipe.

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # Validate the bundle to load all its pipes into the library
    # This ensures all dependencies are available
    await validate_bundle(plx_file_path=bundle_path, library_dirs=library_dirs)

    # Now get the specific pipe and dry-run only that one
    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, raise_on_failure=True)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


def validate_cmd(
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
        typer.Option("--bundle", help="Bundle file path (.plx)"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files)"),
    ] = None,
) -> None:
    """Validate a pipe, bundle, or all pipes and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent validate my_pipe
        pipelex-agent validate my_bundle.plx
        pipelex-agent validate --all -L ./my_pipes
    """
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Handle --all flag
    if validate_all:
        if target or pipe or bundle:
            agent_error("--all cannot be used with a target, --pipe, or --bundle", "ArgumentError")

        make_pipelex_for_agent_cli(library_dirs=library_dirs)

        try:
            result = asyncio.run(_validate_all_core(library_dirs=library_dirs))
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
            if target == "all":
                agent_error(
                    "'all' is not a pipe code. Did you mean '--all'?",
                    "ArgumentError",
                )
            pipe_code = target
            if pipe:
                agent_error("Cannot use --pipe if already passing a pipe code as positional argument", "ArgumentError")

    if bundle:
        bundle_path = Path(bundle)

    if pipe:
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    make_pipelex_for_agent_cli()

    try:
        if bundle_path and pipe_code:
            # Validate a specific pipe within a bundle
            result = asyncio.run(_validate_pipe_in_bundle_core(bundle_path=bundle_path, pipe_code=pipe_code, library_dirs=library_dirs))
        elif bundle_path:
            # Validate the entire bundle
            result = asyncio.run(_validate_bundle_core(bundle_path=bundle_path, library_dirs=library_dirs))
        else:
            # Validate a standalone pipe
            result = asyncio.run(_validate_pipe_core(pipe_code=pipe_code, library_dirs=library_dirs))  # type: ignore[arg-type]

        agent_success(result)

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

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
