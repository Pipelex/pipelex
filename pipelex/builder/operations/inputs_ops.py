"""Core operations for generating input JSON for pipes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pipelex.core.pipes.inputs.input_renderer import build_concept_comments, render_inputs
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.blueprint_selection import select_primary_blueprint
from pipelex.pipeline.validate_bundle import validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def build_inputs_for_pipe(
    *,
    pipe_code: str | None = None,
    mthds_contents: list[str] | None = None,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
    explicit: bool = False,
) -> dict[str, Any]:
    """Generate example input JSON for a pipe.

    Supports loading from either mthds contents, a bundle file path,
    or from already-loaded libraries.

    Args:
        pipe_code: The pipe code to generate inputs for.
        mthds_contents: List of raw .mthds contents to parse and load.
        bundle_path: Path to the bundle file (.mthds).
        library_dirs: List of library directories to search for pipe definitions.
        explicit: When True, emit the ceremonial envelope form; when False (default), the light shape.

    Returns:
        Dictionary with inputs suitable for JSON serialization.

    Raises:
        ValidateBundleError: If bundle validation fails.
        ValueError: If no pipe code can be determined.
    """
    if mthds_contents:
        # validate_bundle opens a library, loads blueprints, and sets it as current.
        # allow_signatures=True: rendering inputs only needs the pipes loaded, not a fully
        # runnable pipeline — so an in-progress bundle with PipeSignature placeholders is fine here.
        validate_bundle_result = await validate_bundle(mthds_contents=mthds_contents, library_dirs=library_dirs, allow_signatures=True)
        blueprints = validate_bundle_result.blueprints
        if not pipe_code:
            # Domain-qualified main pipe of the primary blueprint — the one shared selection rule.
            main_pipe_ref = select_primary_blueprint(blueprints).main_pipe_ref
            if not main_pipe_ref:
                msg = "Bundle does not declare a main_pipe. Specify a pipe code."
                raise ValueError(msg)
            pipe_code = main_pipe_ref
    elif bundle_path:
        # allow_signatures=True: see the mthds_contents branch — rendering inputs tolerates placeholders.
        validate_bundle_result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs, allow_signatures=True)
        bundle_blueprint = validate_bundle_result.blueprints[0]
        if not pipe_code:
            main_pipe_code = bundle_blueprint.main_pipe
            if not main_pipe_code:
                msg = f"Bundle '{bundle_path}' does not declare a main_pipe. Specify a pipe code."
                raise ValueError(msg)
            pipe_code = PipeFactory.make_pipe_ref_with_domain(domain_code=bundle_blueprint.domain, pipe_code=main_pipe_code)
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
        raise ValueError(msg)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    inputs_json_str = render_inputs(the_pipe, indent=2, explicit=explicit)
    inputs_dict = json.loads(inputs_json_str)

    # concept_comments is internal plumbing for the light-TOML emitter (stripped before the JSON
    # envelope is printed); it lets the agent-CLI TOML surface carry the same `# concept:` hints
    # the human `build inputs --format toml` does.
    return {
        "success": True,
        "pipe_code": pipe_code,
        "inputs": inputs_dict,
        "concept_comments": build_concept_comments(the_pipe.inputs),
    }
