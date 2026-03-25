"""Core operations for generating output JSON for pipes."""

from __future__ import annotations

import json
from typing import Any

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.output.output_renderer import render_output
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library
from pipelex.pipeline.validate_bundle import validate_bundle


async def build_output_for_pipe(
    mthds_contents: list[str],
    pipe_code: str,
    output_format: ConceptRepresentationFormat = ConceptRepresentationFormat.SCHEMA,
) -> dict[str, Any]:
    """Generate output JSON representation for a pipe.

    Args:
        mthds_contents: List of raw .mthds contents to parse and load.
        pipe_code: The pipe code to generate output for.
        output_format: Format to generate output in.

    Returns:
        Dictionary with output representation.

    Raises:
        ValidateBundleError: If bundle validation fails.
    """
    validate_bundle_result = await validate_bundle(mthds_contents=mthds_contents)
    blueprints = validate_bundle_result.blueprints

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id)
    library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    output_json_str = render_output(the_pipe, output_format=output_format)

    return json.loads(output_json_str)  # type: ignore[no-any-return]
