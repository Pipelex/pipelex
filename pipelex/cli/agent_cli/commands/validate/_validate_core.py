"""Core async validation logic for the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_pipe_library,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.optionality_warnings import build_optionality_warnings
from pipelex.pipeline.validate_bundle import build_pending_signatures, build_validated_pipes, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def validate_all_core(*, library_dirs: list[Path] | None = None, allow_signatures: bool = False) -> dict[str, Any]:
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
    # This mirrors BundleValidator.acquire_and_validate's lifecycle (acquire → sweep → restore +
    # teardown) inline rather than calling it, because `validate all` is strict-by-default on
    # signatures and must read the LIBRARY-WIDE pending set BEFORE teardown — acquire_and_validate
    # returns only the per-pipe status map and tears the library down before we could compute it.
    prev_library_id = get_current_library_id_or_none()
    acquired_id, _ = acquire_library(
        library_id="",
        library_dirs=[str(library_dir) for library_dir in library_dirs] if library_dirs else None,
    )
    try:
        # acquire_library left the freshly-acquired library current, so the inner sweep targets it
        # (it filters signatures in strict mode itself). The returned map is keyed by namespaced pipe_ref.
        dry_run_results = await BundleValidator().validate_current_library(allow_signatures=allow_signatures)

        # pending_signatures is the library-wide set of still-unimplemented forward declarations;
        # is_runnable = not pending. `validate all` now makes a strict runnability claim (the consumer
        # gates the exit code on it unless --allow-signatures), so both keys ride the envelope.
        pending_signatures = build_pending_signatures(get_pipe_library().get_pipes_dict())
        # warnings: same advisory lint channel as the bundle surfaces — `validate all` has the
        # whole library loaded, which is all the flow context the cross-flow aggregation needs.
        library_pipes = list(get_pipe_library().get_pipes_dict().values())
        return {
            "success": True,
            "is_valid": True,
            "validated_pipes": build_validated_pipes(dry_run_results),
            "total_pipes": len(dry_run_results),
            "pending_signatures": pending_signatures,
            "is_runnable": not pending_signatures,
            "warnings": [
                warning.model_dump(exclude_none=True) for warning in build_optionality_warnings(collect_controller_taint_analyses(library_pipes))
            ],
        }
    finally:
        # Restore the caller's outer current-library FIRST (so the guarantee survives a teardown
        # raise), then tear the acquired library down — mirroring acquire_and_validate / validate_pipe_core.
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        get_library_manager().teardown(library_id=acquired_id)


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
    # successful lenient (--allow-signatures) run. warnings is the advisory lint channel (e.g. the
    # useless-`!` lint) — same item shape as validation errors, never flips the verdict.
    return {
        "success": True,
        "is_valid": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
        "pending_signatures": result.pending_signatures,
        "is_runnable": not result.pending_signatures,
        "warnings": [
            warning.model_dump(exclude_none=True) for warning in build_optionality_warnings(collect_controller_taint_analyses(result.pipes))
        ],
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
            "is_valid": True,
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
    an implemented slice of a partially stubbed bundle. Signatures are never an error (D-B): if the
    requested pipe reaches one, it dry-runs trivially (the placeholder mints a mock); the unsatisfied
    set is reported library-wide via `pending_signatures` / `is_runnable`, never raised. The caller
    (`validate bundle`/`validate method` with `--pipe`) makes no library-wide runnability claim — it
    surfaces `pending_signatures` for information but does not gate its exit code on it.

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
    # library-wide set of still-unimplemented forward declarations. warnings aggregates over the whole
    # loaded bundle (the lint's cross-flow aggregation needs every flow, not just the sliced pipe).
    return {
        "success": True,
        "is_valid": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
        "pending_signatures": result.pending_signatures,
        "is_runnable": not result.pending_signatures,
        "warnings": [
            warning.model_dump(exclude_none=True) for warning in build_optionality_warnings(collect_controller_taint_analyses(result.pipes))
        ],
    }
