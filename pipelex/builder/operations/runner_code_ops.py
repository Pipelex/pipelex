"""Core operations for generating runner code for pipes."""

from __future__ import annotations

from pipelex.builder.runner_code import generate_runner_code
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library
from pipelex.pipeline.bundle_validator import BundleValidator


async def build_runner_code_for_pipe(
    mthds_contents: list[str],
    pipe_code: str,
) -> str:
    """Generate Python runner code for a pipe from .mthds contents.

    Parses and validates the contents, loads pipes, dry-runs them,
    then generates runner code for the specified pipe.

    Args:
        mthds_contents: List of raw .mthds contents to parse and load.
        pipe_code: The pipe code to generate runner code for.

    Returns:
        Generated Python runner code as a string.

    Raises:
        PipelexInterpreterError: If MTHDS content fails to parse or validate.
        PipeValidationError: If pipe validation fails.
        DryRunError: If dry-running the pipes fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id)

    # Parse PLX contents into bundle blueprints
    blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]

    # Load pipes from the blueprints
    pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

    # Validate (static wiring + dry run) against the open library — never tears it down, so the
    # library stays loaded for generate_runner_code below (D6 inner-sweep / loaded-on-success).
    await BundleValidator().validate_pipes(pipes=pipes, library_id=library_id)

    # Get the required pipe and generate runner code
    pipe = get_required_pipe(pipe_code)
    return generate_runner_code(pipe=pipe)
