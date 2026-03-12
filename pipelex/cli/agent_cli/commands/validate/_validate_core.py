"""Core async validation logic for the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.builder.operations.validate_ops import (
    validate_all,
    validate_bundle_file,
    validate_pipe,
    validate_pipe_in_bundle,
)

if TYPE_CHECKING:
    from pathlib import Path


async def validate_all_core(
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
    return await validate_all(library_dirs=library_dirs)


async def validate_bundle_core(
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
    return await validate_bundle_file(bundle_path=bundle_path, library_dirs=library_dirs)


async def validate_pipe_core(
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
    return await validate_pipe(pipe_code=pipe_code, library_dirs=library_dirs)


async def validate_pipe_in_bundle_core(
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
    return await validate_pipe_in_bundle(
        bundle_path=bundle_path,
        pipe_code=pipe_code,
        library_dirs=library_dirs,
    )
