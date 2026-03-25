"""Core operations for validating pipes and bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipe_run.dry_run import DryRunStatus, dry_run_pipe, dry_run_pipes
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
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    pipes = library.pipe_library.get_pipes()
    for the_pipe in pipes:
        the_pipe.validate_with_libraries()

    dry_run_results = await dry_run_pipes(pipes=pipes, raise_on_failure=True)

    validated_pipes: list[dict[str, str]] = []
    for the_pipe in pipes:
        dry_run_output = dry_run_results.get(the_pipe.pipe_ref)
        status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS
        validated_pipes.append({"pipe_code": the_pipe.code, "status": status})

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(pipes),
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
        "pipelex_bundle_blueprint": blueprints[0].model_dump(mode="json")
        if len(blueprints) == 1
        else [b.model_dump(mode="json") for b in blueprints],
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
    await dry_run_pipe(the_pipe, raise_on_failure=True)

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
    # Validate the bundle to load all its pipes into the library
    await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    # Now get the specific pipe and dry-run only that one
    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, raise_on_failure=True)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }
