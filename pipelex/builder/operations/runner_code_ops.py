"""Core operations for generating runner code for pipes."""

from __future__ import annotations

from pipelex.builder.runner_code import generate_runner_code
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library
from pipelex.pipe_run.dry_run import dry_run_pipes


async def build_runner_code_for_pipe(
    mthds_content: str,
    pipe_code: str,
) -> str:
    """Generate Python runner code for a pipe from .mthds content.

    Parses and validates the content, loads pipes, dry-runs them,
    then generates runner code for the specified pipe.

    Args:
        mthds_content: Raw .mthds content to parse and load.
        pipe_code: The pipe code to generate runner code for.

    Returns:
        Generated Python runner code as a string.

    Raises:
        Exception: If parsing, validation, or code generation fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id)

    # Parse PLX content into a bundle blueprint
    converter = PipelexInterpreter()
    blueprint = converter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)

    # Load pipes from the blueprint
    pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

    # Validate all pipes
    for pipe in pipes:
        pipe.validate_with_libraries()
        await dry_run_pipes(pipes=[pipe], raise_on_failure=True)

    # Get the required pipe and generate runner code
    pipe = get_required_pipe(pipe_code)
    return generate_runner_code(pipe=pipe)
