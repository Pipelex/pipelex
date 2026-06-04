"""Core operations for generating runner code for pipes."""

from __future__ import annotations

from pipelex.builder.runner_code import generate_runner_code
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_required_pipe,
    set_current_library,
)
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
    # Capture the caller's outer current-library so a failure can restore it instead of leaving this
    # temporary library current (mirrors validate_bundle's teardown-on-failure-only).
    prev_library_id = get_current_library_id_or_none()
    library_id, _ = library_manager.open_library()
    success = False
    try:
        set_current_library(library_id=library_id)

        # Parse PLX contents into bundle blueprints
        blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]

        # Load pipes from the blueprints
        pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

        # Validate (static wiring + dry run) against the open library — never tears it down, so the
        # library stays loaded for generate_runner_code below (D6 inner-sweep / loaded-on-success).
        await BundleValidator().validate_pipes(pipes=pipes, library_id=library_id)

        # Get the required pipe and generate runner code
        pipe = get_required_pipe(pipe_code)
        runner_code = generate_runner_code(pipe=pipe)
        success = True
        return runner_code
    finally:
        # Loaded-on-success contract (pinned by test_validate_bundle_loaded_on_success): leave the
        # library open + current so the caller can keep using it. On FAILURE this caller owns cleanup —
        # restore the outer current-library FIRST (so the guarantee survives a teardown raise), then tear
        # the temporary library down. set_current_library cannot take None, so route the "no outer was
        # set" case through clear_current_library.
        if not success:
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)
