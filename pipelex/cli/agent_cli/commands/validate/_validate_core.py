"""Core async validation logic for the agent CLI."""

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


async def validate_all_core(
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = True,
) -> dict[str, Any]:
    """Validate all pipes in all libraries.

    Args:
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders. The agent CLI defaults
            to True because authoring workflows routinely contain unresolved signatures.

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

    all_pipes = library.pipe_library.get_pipes()
    # In strict mode, signatures themselves would always fail the pre-check; filter them out.
    pipes = all_pipes if allow_signatures else [pipe for pipe in all_pipes if not pipe.is_signature]
    for the_pipe in pipes:
        the_pipe.validate_with_libraries()

    dry_run_results = await dry_run_pipes(pipes=pipes, allow_signatures=allow_signatures, raise_on_failure=True)

    validated_pipes: list[dict[str, str]] = []
    for the_pipe in pipes:
        dry_run_output = dry_run_results.get(the_pipe.pipe_ref)
        status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS
        validated_pipes.append({"pipe_code": the_pipe.pipe_ref, "status": status})

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(pipes),
    }


async def validate_bundle_core(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = True,
) -> dict[str, Any]:
    """Validate a bundle file.

    Args:
        bundle_path: Path to the bundle file.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders. Defaults to True for
            the agent CLI since signatures are the authoring sweet-spot.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    result = await validate_bundle(
        mthds_file_path=bundle_path,
        library_dirs=library_dirs,
        allow_signatures=allow_signatures,
    )

    validated_pipes = [{"pipe_code": the_pipe.pipe_ref, "status": "SUCCESS"} for the_pipe in result.pipes]

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
    }


async def validate_pipe_core(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = True,
) -> dict[str, Any]:
    """Validate a single pipe.

    Args:
        pipe_code: The pipe code to validate.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders. Defaults to True for
            the agent CLI since signatures are the authoring sweet-spot.

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
    await dry_run_pipe(the_pipe, allow_signatures=allow_signatures, raise_on_failure=True)

    return {
        "success": True,
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


async def validate_pipe_in_bundle_core(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = True,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    This first validates the bundle to load its pipes into the library,
    then validates only the specified pipe.

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders. Defaults to True for
            the agent CLI since signatures are the authoring sweet-spot.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # Validate the bundle to load all its pipes into the library
    # This ensures all dependencies are available
    await validate_bundle(
        mthds_file_path=bundle_path,
        library_dirs=library_dirs,
        allow_signatures=allow_signatures,
    )

    # Now get the specific pipe and dry-run only that one
    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, allow_signatures=allow_signatures, raise_on_failure=True)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }
