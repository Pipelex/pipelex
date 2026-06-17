"""Core logic for generating input JSON in the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.builder.operations.inputs_ops import build_inputs_for_pipe

if TYPE_CHECKING:
    from pathlib import Path


async def inputs_core(
    pipe_code: str | None = None,
    *,
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
    return await build_inputs_for_pipe(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        library_dirs=library_dirs,
    )
