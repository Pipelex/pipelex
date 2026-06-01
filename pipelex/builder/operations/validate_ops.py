"""Core operations for validating pipes and bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.pipeline.validate_bundle import validate_bundle

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

    validated_pipes = [{"pipe_code": dry_run_output.pipe_code, "status": dry_run_output.status} for dry_run_output in dry_run_results.values()]

    return {
        "success": True,
        "validated_pipes": validated_pipes,
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

    validated_pipes: list[dict[str, str]] = []
    for the_pipe in result.pipes:
        dry_run_output = result.dry_run_result.get(the_pipe.pipe_ref)
        status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS
        validated_pipes.append({"pipe_code": the_pipe.code, "status": status})

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
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

    validated_pipes: list[dict[str, str]] = []
    for the_pipe in validate_bundle_result.pipes:
        dry_run_output = validate_bundle_result.dry_run_result.get(the_pipe.pipe_ref)
        status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS
        validated_pipes.append({"pipe_code": the_pipe.code, "status": status})

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
        "validated_pipes": [{"pipe_code": pipe_code, "status": dry_run_results[the_pipe.pipe_ref].status}],
        "total_pipes": 1,
    }


async def validate_pipe_in_bundle(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    This first validates the bundle to load its pipes into the library,
    then validates only the specified pipe.

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # Validate the bundle to load all its pipes into the library — the sweep already classified the
    # requested pipe, so read its status from the result map instead of re-running a redundant dry run.
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    dry_run_output = result.dry_run_result.get(the_pipe.pipe_ref)
    status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": status}],
        "total_pipes": 1,
    }
