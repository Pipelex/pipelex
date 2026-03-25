"""Core operations for generating output JSON for pipes."""

from __future__ import annotations

import json
from typing import Any

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.output.output_renderer import render_output
from pipelex.hub import get_required_pipe
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
    # validate_bundle opens a library, loads blueprints, and sets it as current
    await validate_bundle(mthds_contents=mthds_contents)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    output_str = render_output(the_pipe, output_format=output_format)

    match output_format:
        case ConceptRepresentationFormat.PYTHON:
            return {"output": output_str}
        case ConceptRepresentationFormat.SCHEMA | ConceptRepresentationFormat.JSON:
            return json.loads(output_str)  # type: ignore[no-any-return]
