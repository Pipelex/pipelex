"""Core async validation logic for the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    get_own_pipes,
    get_pipe_library,
    get_required_entry_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipeline.advisory_warnings import collect_advisory_warnings, collect_current_library_entry_pipe_refs
from pipelex.pipeline.blueprint_selection import collect_entry_pipe_refs
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.dry_run_warnings import build_dry_run_warnings
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.tree_files_read import tree_files_envelope_fields
from pipelex.pipeline.usage_stats_reporting import MethodValidationReport
from pipelex.pipeline.validate_bundle import build_pending_signatures, build_validated_pipes, validate_bundle
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error

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
    with MethodValidationReport() as validation_report:
        prev_library_id = get_current_library_id_or_none()
        # A refusal of the libraries while loading them is the invalid verdict, through the shared
        # bundle-loading cascade, as on `validate bundle`. The directories are the caller's own, so
        # acquire_library translates their load itself, while the library is still current: the translation
        # reads the library's pipe sources to locate an item, and a translation around the call would run
        # only after acquire_library had torn the failed library down, leaving the item without its file.
        # The sweep below stays untranslated on purpose: a failing dry run is answered as the DryRunError it
        # is, as on `validate pipe`.
        acquired_id, _ = acquire_library(
            library_id="",
            library_dirs=[str(library_dir) for library_dir in library_dirs] if library_dirs else None,
            library_dirs_are_callers=True,
        )
        try:
            validation_report.describe(pipes=get_own_pipes())
            # acquire_library left the freshly-acquired library current, so the inner sweep targets it
            # (it filters signatures in strict mode itself). The returned map is keyed by namespaced pipe_ref.
            # A pipe whose dry run fails is the invalid verdict, one located dry_run item per failing pipe,
            # through the same cascade and item builder as `validate bundle`.
            with translate_to_validate_bundle_error():
                dry_run_results = await BundleValidator().validate_current_library(allow_signatures=allow_signatures, collect_dry_run_warnings=True)

            # pending_signatures is the library-wide set of still-unimplemented forward declarations;
            # is_runnable = not pending. `validate all` now makes a strict runnability claim (the consumer
            # gates the exit code on it unless --allow-signatures), so both keys ride the envelope.
            pending_signatures = build_pending_signatures(get_pipe_library().get_pipes_dict())
            # warnings: same advisory lint channel as the bundle surfaces — `validate all` has the
            # whole library loaded, which is all the flow context the cross-flow aggregation needs.
            # Its entry pipes come off the blueprints the library manager accumulated on the way in;
            # there is no `ValidateBundleResult` on this path to read a `main_pipe` from.
            library_pipes = list(get_pipe_library().get_pipes_dict().values())
            warnings = collect_advisory_warnings(
                pipes=library_pipes,
                entry_pipe_refs=collect_current_library_entry_pipe_refs(),
                dry_run_result=dry_run_results,
            )
            validation_report.count_warnings(count=len(warnings))
            return {
                "success": True,
                "is_valid": True,
                "validated_pipes": build_validated_pipes(dry_run_results),
                "total_pipes": len(dry_run_results),
                "pending_signatures": pending_signatures,
                "is_runnable": not pending_signatures,
                "warnings": [warning.model_dump(exclude_none=True) for warning in warnings],
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
    with MethodValidationReport() as validation_report:
        result = await validate_bundle(
            mthds_file_path=bundle_path,
            library_dirs=library_dirs,
            allow_signatures=allow_signatures,
            collect_dry_run_warnings=True,
        )
        warnings = collect_advisory_warnings(
            pipes=result.pipes,
            entry_pipe_refs=collect_entry_pipe_refs(result.blueprints),
            dry_run_result=result.dry_run_result,
        )
        validation_report.describe(pipes=result.pipes)
        validation_report.count_warnings(count=len(warnings))

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
        "warnings": [warning.model_dump(exclude_none=True) for warning in warnings],
        # The files of the method's tree each loaded pipe reads, and who reads each, as the canonical report states them.
        **tree_files_envelope_fields(pipes=result.pipes),
    }


async def validate_method_folder_core(
    *,
    method_dir: Path,
    library_dirs: list[Path] | None,
    allow_signatures: bool,
    pipe_code: str | None,
) -> dict[str, Any]:
    """Validate a method's folder whole: every bundle of its method tree, as the MTHDS protocol's validation judges a method.

    The folder needs no pipe to start at. Every pipe its bundles define is dry-run, or only ``pipe_code`` when one is
    named, while the whole tree still loads; the ``library_dirs`` load beside it for its bundles to use and are not
    judged.

    Args:
        method_dir: The method's folder.
        library_dirs: The folder and the ``-L`` directories, the caller's own.
        allow_signatures: Whether to accept PipeSignature placeholders in the dependency graph.
        pipe_code: The one pipe to dry-run, or None for every pipe of the method.

    Returns:
        Dictionary with validation results suitable for JSON serialization, ``bundle_path`` naming the folder.

    Raises:
        ValidateBundleError: If validation fails.
        EntryPipeNotFoundError: If ``pipe_code`` is defined by no bundle of the method.
    """
    with MethodValidationReport() as validation_report:
        result = await validate_bundle(
            method_dir=method_dir,
            library_dirs=library_dirs,
            library_dirs_are_callers=True,
            allow_signatures=allow_signatures,
            dry_run_pipe_codes=[pipe_code] if pipe_code else None,
            collect_dry_run_warnings=True,
        )
        warnings = collect_advisory_warnings(
            pipes=result.pipes,
            entry_pipe_refs=collect_entry_pipe_refs(result.blueprints),
            dry_run_result=result.dry_run_result,
        )
        validation_report.describe(pipes=result.pipes)
        validation_report.count_warnings(count=len(warnings))

    return {
        "success": True,
        "is_valid": True,
        "bundle_path": str(method_dir),
        "validated_pipes": build_validated_pipes(result.dry_run_result),
        "total_pipes": len(result.dry_run_result),
        "pending_signatures": result.pending_signatures,
        "is_runnable": not result.pending_signatures,
        "warnings": [warning.model_dump(exclude_none=True) for warning in warnings],
        # The files of the method's tree each loaded pipe reads, and who reads each, as the canonical report states them.
        **tree_files_envelope_fields(pipes=result.pipes),
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
    with MethodValidationReport() as validation_report:
        library_manager = get_library_manager()
        # Capture the caller's outer current-library so it can be restored after this temporary validation
        # library is torn down.
        prev_library_id = get_current_library_id_or_none()
        library_id, _ = library_manager.open_library()
        try:
            set_current_library(library_id=library_id)
            effective_dirs, _ = resolve_library_dirs(library_dirs)

            if effective_dirs:
                # A refusal of the libraries while loading them is the invalid verdict, through the shared
                # bundle-loading cascade, as on `validate bundle`.
                with translate_to_validate_bundle_error():
                    library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

            # The entry-pipe lookup stays outside the cascade: a code naming no pipe is no verdict. A pipe whose
            # dry run fails is the invalid verdict, one located dry_run item per failing pipe, as on `validate bundle`.
            the_pipe = get_required_entry_pipe(pipe_code=pipe_code)
            validation_report.describe(pipes=get_own_pipes())
            with translate_to_validate_bundle_error():
                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=[the_pipe], library_id=library_id, allow_signatures=allow_signatures, collect_dry_run_warnings=True
                )

            # warnings: what the pipe's dry run found without failing, such as a template check's warnings. None
            # of the bundle-wide lints ride here: one pipe makes no bundle-wide claim, so there is no flow to lint.
            warnings = build_dry_run_warnings(dry_run_results)
            validation_report.count_warnings(count=len(warnings))
            return {
                "success": True,
                "is_valid": True,
                "validated_pipes": build_validated_pipes(dry_run_results),
                "total_pipes": len(dry_run_results),
                "warnings": [warning.model_dump(exclude_none=True) for warning in warnings],
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
        EntryPipeNotFoundError: If `pipe_code` is not defined in the bundle. The caller-supplied
            selector makes it INPUT-domained; it is a `PipeNotFoundError` subclass, so an existing
            `except PipeNotFoundError` still catches it.
    """
    with MethodValidationReport() as validation_report:
        result = await validate_bundle(
            mthds_file_path=bundle_path,
            library_dirs=library_dirs,
            allow_signatures=allow_signatures,
            dry_run_pipe_codes=[pipe_code],
            collect_dry_run_warnings=True,
        )
        warnings = collect_advisory_warnings(
            pipes=result.pipes,
            entry_pipe_refs=collect_entry_pipe_refs(result.blueprints),
            dry_run_result=result.dry_run_result,
        )
        validation_report.describe(pipes=result.pipes)
        validation_report.count_warnings(count=len(warnings))

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
        "warnings": [warning.model_dump(exclude_none=True) for warning in warnings],
        # The files of the method's tree each loaded pipe reads, and who reads each, as the canonical report states them.
        **tree_files_envelope_fields(pipes=result.pipes),
    }
