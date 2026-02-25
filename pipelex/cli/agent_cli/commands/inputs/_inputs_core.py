"""Core logic for generating input JSON in the agent CLI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pipelex.core.pipes.inputs.input_renderer import render_inputs
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def inputs_core(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe code to generate inputs for.
        bundle_path: Path to the bundle file (.mthds).
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with inputs suitable for JSON serialization.

    Raises:
        ValidateBundleError: If bundle validation fails.
        NoInputsRequiredError: If the pipe has no inputs.
    """
    if bundle_path:
        validate_bundle_result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)
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
