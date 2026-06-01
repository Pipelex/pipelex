"""Core async validation logic for the agent CLI."""

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

    # use_ref=True: the agent all-pipes surface keys entries by the namespaced pipe_ref.
    return {
        "success": True,
        "validated_pipes": build_validated_pipes(dry_run_results, use_ref=True),
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
    # failures and SKIPPED cross-package pipes the dry-run actually recorded (C-8). use_ref=True keys
    # entries by the namespaced pipe_ref (the agent bundle surface's identity contract).
    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result, use_ref=True),
        "total_pipes": len(result.dry_run_result),
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

    # use_ref=False: the single-pipe slice keys its one entry by the bare pipe code.
    return {
        "success": True,
        "validated_pipes": build_validated_pipes(dry_run_results),
        "total_pipes": len(dry_run_results),
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
    result = await validate_bundle(
        mthds_file_path=bundle_path,
        library_dirs=library_dirs,
        allow_signatures=allow_signatures,
        dry_run_pipe_codes=[pipe_code],
    )

    # Consume the real per-pipe status from the sliced sweep — a fixed "SUCCESS" would hide an allowed
    # failure or a cross-package SKIPPED the dry-run actually recorded (C-8). use_ref=False keys the one
    # entry by the bare pipe code, matching the single-pipe slice contract.
    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
    }
