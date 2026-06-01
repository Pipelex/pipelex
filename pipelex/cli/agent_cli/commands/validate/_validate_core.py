"""Core async validation logic for the agent CLI."""

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


async def validate_all_core(
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> dict[str, Any]:
    """Validate all pipes in all libraries.

    Args:
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders in the dependency graph.
            Defaults to False (strict) — matches `pipelex validate`.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # acquire_and_validate opens a fresh library, loads the resolved dirs, sweeps every loaded pipe
    # (filtering signatures in strict mode), and tears the library down — the standalone validate-all
    # lifecycle (D6). The returned map is keyed by namespaced pipe_ref.
    dry_run_results = await BundleValidator().acquire_and_validate(
        library_dirs=[str(library_dir) for library_dir in library_dirs] if library_dirs else None,
        allow_signatures=allow_signatures,
    )

    validated_pipes = [{"pipe_code": dry_run_output.pipe_ref, "status": dry_run_output.status} for dry_run_output in dry_run_results.values()]

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(dry_run_results),
    }


async def validate_bundle_core(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> dict[str, Any]:
    """Validate a bundle file.

    Args:
        bundle_path: Path to the bundle file.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders in the dependency graph.
            Defaults to False (strict) — matches `pipelex validate`.

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

    # Consume the real per-pipe status from the sweep — a fixed all-"SUCCESS" list would hide allowed
    # failures and SKIPPED cross-package pipes the dry-run actually recorded (C-8).
    validated_pipes: list[dict[str, str]] = []
    for the_pipe in result.pipes:
        dry_run_output = result.dry_run_result.get(the_pipe.pipe_ref)
        status: str = dry_run_output.status if dry_run_output else DryRunStatus.SUCCESS
        validated_pipes.append({"pipe_code": the_pipe.pipe_ref, "status": status})

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
    }


async def validate_pipe_core(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> dict[str, Any]:
    """Validate a single pipe.

    Args:
        pipe_code: The pipe code to validate.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders in the dependency graph.
            Defaults to False (strict) — matches `pipelex validate`.

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
    dry_run_results = await BundleValidator().validate_pipes(pipes=[the_pipe], library_id=library_id, allow_signatures=allow_signatures)

    return {
        "success": True,
        "validated_pipes": [{"pipe_code": pipe_code, "status": dry_run_results[the_pipe.pipe_ref].status}],
        "total_pipes": 1,
    }


async def validate_pipe_in_bundle_core(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    Loads the bundle's pipes into the library (so the requested pipe's dependencies resolve),
    then dry-runs ONLY the requested pipe. Unrelated pipes — including unimplemented
    `PipeSignature` placeholders — are loaded but not dry-run, so they do not block validating
    an implemented slice of a partially stubbed bundle. Strict mode is still enforced on the
    requested pipe: if it reaches a signature, validation fails.

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.
        allow_signatures: Whether to accept PipeSignature placeholders in the dependency graph.
            Defaults to False (strict) — matches `pipelex validate`.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
        PipeNotFoundError: If `pipe_code` is not defined in the bundle.
    """
    await validate_bundle(
        mthds_file_path=bundle_path,
        library_dirs=library_dirs,
        allow_signatures=allow_signatures,
        dry_run_pipe_codes=[pipe_code],
    )

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }
