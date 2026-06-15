"""Core async validation logic for the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
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
    *,
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

    # No `pending_signatures` here by design — see validate_all in builder/operations/validate_ops.py:
    # it is a per-bundle top-down-build nudge surfaced only by `validate bundle`, not the whole-library sweep.
    return {
        "success": True,
        "validated_pipes": build_validated_pipes(dry_run_results),
        "total_pipes": len(dry_run_results),
    }


async def validate_bundle_core(
    bundle_path: Path,
    *,
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
    # failures and SKIPPED cross-package pipes the dry-run actually recorded (C-8). pending_signatures
    # is the library-wide set of still-unimplemented forward declarations — a non-blocking nudge on a
    # successful lenient (--allow-signatures) run.
    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
        "pending_signatures": result.pending_signatures,
        "is_runnable": not result.pending_signatures,
    }


async def validate_pipe_core(
    pipe_code: str,
    *,
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
    # Capture the caller's outer current-library so it can be restored after this temporary validation
    # library is torn down (mirrors the builder validate_ops.validate_pipe twin).
    prev_library_id = get_current_library_id_or_none()
    library_id, _ = library_manager.open_library()
    try:
        set_current_library(library_id=library_id)
        effective_dirs, _ = resolve_library_dirs(library_dirs)

        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

        the_pipe = get_required_pipe(pipe_code=pipe_code)
        dry_run_results = await BundleValidator().validate_pipes(pipes=[the_pipe], library_id=library_id, allow_signatures=allow_signatures)

        return {
            "success": True,
            "validated_pipes": build_validated_pipes(dry_run_results),
            "total_pipes": len(dry_run_results),
        }
    finally:
        # validate_pipes is the D6 inner sweep and never tears the library down, and validate_pipe_core
        # does not need the library after returning its results dict — so this caller owns the full
        # lifecycle on BOTH paths. Restore the outer current-library FIRST (so the guarantee survives a
        # teardown raise), then tear the temporary library down. set_current_library cannot take None,
        # so route the "no outer was set" case through clear_current_library.
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        library_manager.teardown(library_id=library_id)


async def validate_pipe_in_bundle_core(
    *,
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
    # failure or a cross-package SKIPPED the dry-run actually recorded (C-8). pending_signatures is the
    # library-wide set of still-unimplemented forward declarations.
    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
        "pending_signatures": result.pending_signatures,
        "is_runnable": not result.pending_signatures,
    }
