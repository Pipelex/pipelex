"""Path-to-bundle resolution for agent CLI bundle commands.

``validate bundle`` and ``fix bundle`` must resolve the user's ``path`` argument identically —
fix must patch exactly the file validate judged. The shared core owns the filesystem
decision-making; this wrapper owns agent error envelopes.
"""

from pathlib import Path
from typing import NoReturn

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.cli.bundle_target_resolution import (
    BundleTargetResolutionError,
    BundleTargetResolutionErrorKind,
    BundleTargetResolutionSuccess,
    resolve_bundle_target_core,
)


def _stringify_library_dirs(library_dirs: list[Path] | None) -> list[str] | None:
    if library_dirs is None:
        return None
    return [str(library_dir) for library_dir in library_dirs]


def _handle_resolution_error(error: BundleTargetResolutionError) -> NoReturn:
    match error.kind:
        case BundleTargetResolutionErrorKind.NO_MTHDS_FILE:
            agent_error(f"No .mthds bundle file found in directory '{error.input_path}'", error_type="FileNotFoundError", exit_code=2)
        case BundleTargetResolutionErrorKind.AMBIGUOUS_MTHDS_FILES:
            mthds_names = ", ".join(mthds_file.name for mthds_file in error.candidate_files)
            agent_error(
                f"Multiple .mthds files found in '{error.input_path}' ({mthds_names}) and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                f"Pass the .mthds file directly instead.",
                error_type="ArgumentError",
                exit_code=2,
            )
        case BundleTargetResolutionErrorKind.UNSAFE_AUTO_DETECTED_SYMLINK:
            agent_error(
                f"Refusing to auto-detect symlinked bundle '{error.candidate_files[0]}'. Pass a regular .mthds file inside the directory.",
                error_type="ArgumentError",
                exit_code=2,
            )
        case BundleTargetResolutionErrorKind.NOT_BUNDLE_TARGET:
            agent_error(
                f"'{error.input_path}' is not a .mthds file or directory. "
                f"Use 'validate pipe <code>' for pipe codes, or 'validate bundle <path>' for .mthds files/directories.",
                error_type="ArgumentError",
                exit_code=2,
            )


def resolve_bundle_target(path: str, *, library_dir: list[str] | None) -> tuple[str, list[str] | None]:
    """Resolve a ``path`` CLI argument into ``(bundle_path, library_dir)``.

    Directory mode auto-detects the bundle file — ``DEFAULT_BUNDLE_FILE_NAME`` if present, else
    a single ``*.mthds`` — and prepends the directory itself to ``library_dir`` so sibling
    files load (and, being user-passed, fall inside the fix write scope). No file / multiple
    ambiguous files / not-a-``.mthds`` path exit 2 via ``agent_error`` (no verdict produced).

    Both ``path`` and each ``library_dir`` entry have ``~`` expanded before resolution, so
    home-relative inputs behave like every other CLI path argument.

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a bundle directory).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.

    Returns:
        ``(bundle_path, library_dir)`` — the resolved bundle file path, and the possibly
        directory-augmented library dirs (``None`` when none apply).
    """
    result = resolve_bundle_target_core(path, library_dir=library_dir)
    if isinstance(result, BundleTargetResolutionSuccess):
        return str(result.bundle_path), _stringify_library_dirs(result.library_dirs)

    _handle_resolution_error(result)
