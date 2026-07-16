"""Core operations for validating pipes and bundles."""

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
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.optionality_warnings import build_optionality_warnings
from pipelex.pipeline.validate_bundle import build_validated_pipes, validate_bundle

if TYPE_CHECKING:
    from pathlib import Path


async def validate_all(
    *,
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

    # No `pending_signatures` here by design: it is a per-bundle, top-down-build nudge ("which headers
    # are still unimplemented in this bundle"), surfaced only by `validate bundle`. The validate-all
    # sweep is a whole-library check, not a build step — and `acquire_and_validate` tears its library
    # down before returning, so the set could not be computed post-hoc without reshaping a shared method.
    return {
        "success": True,
        "is_valid": True,
        "validated_pipes": build_validated_pipes(dry_run_results),
        "total_pipes": len(dry_run_results),
    }


async def validate_bundle_file(
    bundle_path: Path,
    *,
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

    # warnings is the advisory lint channel (e.g. the useless-`!` lint) — same item shape as
    # validation errors, never flips the verdict. Mirrors the agent-CLI validate_bundle_core twin.
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
        "is_valid": True,
        "mthds_contents": mthds_contents,
        "pipelex_bundle_blueprint": [b.model_dump(mode="json") for b in blueprints],
        "validated_pipes": build_validated_pipes(validate_bundle_result.dry_run_result),
        "total_pipes": len(validate_bundle_result.dry_run_result),
        "pending_signatures": validate_bundle_result.pending_signatures,
        "is_runnable": not validate_bundle_result.pending_signatures,
        "warnings": [
            warning.model_dump(exclude_none=True)
            for warning in build_optionality_warnings(collect_controller_taint_analyses(validate_bundle_result.pipes))
        ],
    }


async def validate_pipe(
    pipe_code: str,
    *,
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
    # Capture the caller's outer current-library so it can be restored after this temporary validation
    # library is torn down (mirrors acquire_and_validate / validate_bundle).
    prev_library_id = get_current_library_id_or_none()
    library_id, _ = library_manager.open_library()
    try:
        set_current_library(library_id=library_id)
        effective_dirs, _ = resolve_library_dirs(library_dirs)

        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

        the_pipe = get_required_pipe(pipe_code=pipe_code)
        dry_run_results = await BundleValidator().validate_pipes(pipes=[the_pipe], library_id=library_id)

        return {
            "success": True,
            "is_valid": True,
            "validated_pipes": build_validated_pipes(dry_run_results),
            "total_pipes": len(dry_run_results),
        }
    finally:
        # validate_pipes is the D6 inner sweep and never tears the library down, and validate_pipe does
        # not need the library after returning its results dict — so this caller owns the full lifecycle
        # on BOTH paths. Restore the outer current-library FIRST (so the guarantee survives a teardown
        # raise), then tear the temporary library down. set_current_library cannot take None, so route
        # the "no outer was set" case through clear_current_library.
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            clear_current_library()
        library_manager.teardown(library_id=library_id)


async def validate_pipe_in_bundle(
    *,
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

    # warnings aggregates over the whole loaded bundle (the lint's cross-flow aggregation needs
    # every flow, not just the sliced pipe). Mirrors the agent-CLI validate_pipe_in_bundle_core twin.
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
