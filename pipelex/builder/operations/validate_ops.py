"""Core operations for validating pipes and bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.validate_bundle import dry_run_loaded_pipes_or_raise, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def validate_all(
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all pipes in all libraries."""
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    pipes = library.pipe_library.get_pipes()
    for the_pipe in pipes:
        the_pipe.validate_with_libraries()

    await dry_run_loaded_pipes_or_raise(
        pipe_refs=[the_pipe.pipe_ref for the_pipe in pipes],
        library_id=library_id,
    )

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in pipes]

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(pipes),
    }


async def validate_bundle_file(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a bundle file."""
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in result.pipes]

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
    }


async def validate_bundle_content(
    mthds_contents: list[str],
) -> dict[str, Any]:
    """Validate bundle content provided as strings."""
    validate_bundle_result = await validate_bundle(mthds_contents=mthds_contents)
    blueprints = validate_bundle_result.blueprints

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in validate_bundle_result.pipes]

    return {
        "success": True,
        "mthds_contents": mthds_contents,
        "pipelex_bundle_blueprint": [b.model_dump(mode="json") for b in blueprints],
        "validated_pipes": validated_pipes,
        "total_pipes": len(validate_bundle_result.pipes),
    }


async def validate_pipe(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe."""
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_loaded_pipes_or_raise(pipe_refs=[the_pipe.pipe_ref], library_id=library_id)

    return {
        "success": True,
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


async def validate_pipe_in_bundle(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    Validates the full bundle (which dry-runs every pipe) and confirms the requested
    pipe is in the bundle's loaded set.
    """
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)
    if not any(pipe_code in {the_pipe.pipe_ref, the_pipe.code} for the_pipe in result.pipes):
        get_required_pipe(pipe_code=pipe_code)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }
