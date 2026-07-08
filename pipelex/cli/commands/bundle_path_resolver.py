"""Path-to-bundle resolution for human CLI bundle commands.

``pipelex validate bundle`` and ``pipelex fix bundle`` must resolve the user's ``path``
argument identically: fix must patch exactly the file validate judged. The shared core owns
the filesystem decision-making; this wrapper owns human text-stream errors.
"""

from pathlib import Path
from typing import NoReturn

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
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


def _handle_resolution_error(
    error: BundleTargetResolutionError,
    *,
    command: str,
    not_a_bundle_hint: str,
) -> NoReturn:
    match error.kind:
        case BundleTargetResolutionErrorKind.NO_MTHDS_FILE:
            typer.secho(
                f"Failed to {command}: no .mthds bundle file found in directory '{error.input_path}'",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)
        case BundleTargetResolutionErrorKind.AMBIGUOUS_MTHDS_FILES:
            mthds_names = ", ".join(mthds_file.name for mthds_file in error.candidate_files)
            example_target = error.target_path / error.candidate_files[0].name
            typer.secho(
                f"Failed to {command}: multiple .mthds files found in '{error.input_path}' ({mthds_names}) "
                f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                f"Pass the .mthds file directly, e.g.: pipelex {command} bundle {example_target}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)
        case BundleTargetResolutionErrorKind.NOT_BUNDLE_TARGET:
            typer.secho(
                f"Failed to {command}: '{error.input_path}' is not a .mthds file or directory.\n{not_a_bundle_hint}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)


def resolve_bundle_target(
    path: str,
    *,
    library_dir: list[str] | None,
    command: str,
    not_a_bundle_hint: str,
) -> tuple[str, list[str] | None]:
    """Resolve a ``path`` CLI argument into ``(bundle_path, library_dir)``.

    Directory mode auto-detects the bundle file — ``DEFAULT_BUNDLE_FILE_NAME`` if present, else
    a single ``*.mthds`` — and prepends the directory itself to ``library_dir`` so sibling
    files load (and, being user-passed, fall inside the fix write scope). No file / multiple
    ambiguous files / not-a-``.mthds`` path exit 2 (no verdict produced) with a red message on
    stderr.

    Both ``path`` and each ``library_dir`` entry have ``~`` expanded before resolution, so
    home-relative inputs behave like every other CLI path argument.

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a bundle directory).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.
        command: The human command name (e.g. ``"validate"``, ``"fix"``), used in error
            messages (``Failed to {command}: ...``, ``pipelex {command} bundle ...``).
        not_a_bundle_hint: Command-specific usage hint appended when ``path`` is neither a
            ``.mthds`` file nor a directory.

    Returns:
        ``(bundle_path, library_dir)`` — the resolved bundle file path, and the possibly
        directory-augmented library dirs (``None`` when none apply).
    """
    result = resolve_bundle_target_core(path, library_dir=library_dir)
    if isinstance(result, BundleTargetResolutionSuccess):
        bundle_path = str(result.bundle_path)
        if result.auto_detected:
            typer.echo(f"Auto-detected bundle: {bundle_path}")
        return bundle_path, _stringify_library_dirs(result.library_dirs)

    _handle_resolution_error(result, command=command, not_a_bundle_hint=not_a_bundle_hint)
