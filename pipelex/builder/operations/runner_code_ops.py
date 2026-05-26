"""Core operations for generating runner code for pipes."""

from __future__ import annotations

from pipelex.builder.runner_code import generate_runner_code
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library
from pipelex.pipeline.validate_bundle import dry_run_loaded_pipes_or_raise


async def build_runner_code_for_pipe(
    mthds_contents: list[str],
    pipe_code: str,
) -> str:
    """Generate Python runner code for a pipe from .mthds contents.

    Parses and validates the contents, loads pipes, dry-runs them, then generates
    runner code for the specified pipe.

    Raises:
        MthdsDecodeError: If MTHDS content has TOML syntax errors.
        PipeValidationError: If pipe validation fails.
        PipeRunError: If dry-running any pipe fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id)

    blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]

    pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

    for pipe in pipes:
        pipe.validate_with_libraries()
    await dry_run_loaded_pipes_or_raise(
        pipe_refs=[pipe.pipe_ref for pipe in pipes],
        library_id=library_id,
    )

    pipe = get_required_pipe(pipe_code)
    return generate_runner_code(pipe=pipe)
