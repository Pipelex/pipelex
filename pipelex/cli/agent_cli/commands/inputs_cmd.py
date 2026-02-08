"""Agent CLI inputs command - generate example inputs for a pipe with JSON output."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.core.pipes.inputs.input_renderer import render_inputs
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle


async def _inputs_core(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe code to generate inputs for.
        bundle_path: Path to the bundle file (.plx).
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with inputs suitable for JSON serialization.

    Raises:
        ValidateBundleError: If bundle validation fails.
        NoInputsRequiredError: If the pipe has no inputs.
    """
    if bundle_path:
        validate_bundle_result = await validate_bundle(plx_file_path=bundle_path, library_dirs=library_dirs)
        bundle_blueprint = validate_bundle_result.blueprints[0]
        if not pipe_code:
            main_pipe_code = bundle_blueprint.main_pipe
            if not main_pipe_code:
                msg = f"Bundle '{bundle_path}' does not declare a main_pipe. Specify a pipe code with --pipe."
                raise ValidateBundleError(message=msg)
            pipe_code = main_pipe_code
    else:
        # No bundle - initialize the library manually
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        effective_dirs, _ = resolve_library_dirs(library_dirs)
        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    if not pipe_code:
        msg = "No pipe code specified"
        raise ValidateBundleError(message=msg)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    inputs_json_str = render_inputs(the_pipe, indent=2)
    inputs_dict = json.loads(inputs_json_str)

    return {
        "success": True,
        "pipe_code": pipe_code,
        "inputs": inputs_dict,
    }


def inputs_cmd(
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
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.plx files)"),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs my_pipe
        pipelex-agent inputs my_bundle.plx
        pipelex-agent inputs my_bundle.plx --pipe my_pipe
        pipelex-agent inputs my_pipe -L ./my_pipes
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
                f"'{target}' is a directory. The inputs command requires a .plx file or a pipe code.",
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
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS, library_dirs=library_dirs)

    try:
        result = asyncio.run(_inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, library_dirs=library_dirs))
        agent_success(result)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", "FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        agent_error(exc.message, "ValidateBundleError", cause=exc)

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
            model_type=exc.model_type,
            model_choice=exc.model_choice,
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
