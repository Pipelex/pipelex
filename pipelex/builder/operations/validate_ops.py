"""Core operations for validating pipes and bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.validate_bundle import build_validated_pipes, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def validate_all(
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all pipes in all libraries.

    Args:
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # acquire_and_validate opens a fresh library, loads the resolved dirs, sweeps every loaded pipe,
    # and tears the library down — the standalone validate-all lifecycle (D6).
    dry_run_results = await BundleValidator().acquire_and_validate(
        library_dirs=[str(library_dir) for library_dir in library_dirs] if library_dirs else None,
    )

    return {
        "success": True,
        "validated_pipes": build_validated_pipes(dry_run_results),
        "total_pipes": len(dry_run_results),
    }


async def validate_bundle_file(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a bundle file.

    Args:
        bundle_path: Path to the bundle file.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
    }


async def validate_bundle_content(
    mthds_contents: list[str],
) -> dict[str, Any]:
    """Validate bundle content provided as strings.

    Args:
        mthds_contents: List of raw .mthds contents to validate.

    Returns:
        Dictionary with validation results including the blueprint.

    Raises:
        ValidateBundleError: If validation fails.
    """
    validate_bundle_result = await validate_bundle(mthds_contents=mthds_contents)
    blueprints = validate_bundle_result.blueprints

    return {
        "success": True,
        "mthds_contents": mthds_contents,
        "pipelex_bundle_blueprint": [b.model_dump(mode="json") for b in blueprints],
        "validated_pipes": build_validated_pipes(validate_bundle_result.dry_run_result),
        "total_pipes": len(validate_bundle_result.dry_run_result),
    }


async def validate_pipe(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe.

    Args:
        pipe_code: The pipe code to validate.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    dry_run_results = await BundleValidator().validate_pipes(pipes=[the_pipe], library_id=library_id)

    return {
        "success": True,
        "validated_pipes": build_validated_pipes(dry_run_results),
        "total_pipes": len(dry_run_results),
    }


async def validate_pipe_in_bundle(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    Loads the bundle's pipes into the library (so the requested pipe's dependencies resolve), then
    dry-runs ONLY the requested pipe via ``dry_run_pipe_codes`` — so an unrelated unimplemented
    ``PipeSignature`` or failing sibling does not block validating one implemented slice. ``validate_bundle``
    raises ``PipeNotFoundError`` when ``pipe_code`` is not defined in the bundle (no vacuous success).

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
        PipeNotFoundError: If ``pipe_code`` is not defined in the bundle.
    """
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs, dry_run_pipe_codes=[pipe_code])

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
    }
