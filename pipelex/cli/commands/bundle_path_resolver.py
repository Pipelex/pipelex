"""Shared path→bundle resolution for human CLI bundle commands.

``pipelex validate bundle`` and ``pipelex fix bundle`` must resolve the user's ``path``
argument identically — fix must patch exactly the file validate judged. One helper owns the
resolution: a ``.mthds`` file is taken as-is; a directory auto-detects the default bundle
file name (or a single ``*.mthds``), errors loudly on ambiguity, and injects itself into the
library dirs (making it part of the per-call write scope). The agent CLI has its own twin
(``agent_cli/commands/bundle_path_resolver.py``); the two differ only in error presentation
(human text stream vs agent error envelope).
"""

from pathlib import Path

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


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
    # Expand ``~`` up front so home-relative inputs resolve like every other CLI path arg. Library
    # dirs are expanded first so the directory-mode membership check below compares like-for-like.
    library_dir = [str(Path(lib_dir).expanduser()) for lib_dir in library_dir] if library_dir else None
    target_path = Path(path).expanduser()

    if target_path.is_dir():
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                typer.secho(
                    f"Failed to {command}: no .mthds bundle file found in directory '{path}'",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(2)
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                typer.secho(
                    f"Failed to {command}: multiple .mthds files found in '{path}' ({mthds_names}) "
                    f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly, e.g.: pipelex {command} bundle {target_path / mthds_files[0].name}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(2)
            bundle_path = str(mthds_files[0])

        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

        typer.echo(f"Auto-detected bundle: {bundle_path}")
        return bundle_path, library_dir

    if is_pipelex_file(target_path):
        return str(target_path), library_dir

    typer.secho(
        f"Failed to {command}: '{path}' is not a .mthds file or directory.\n{not_a_bundle_hint}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(2)
