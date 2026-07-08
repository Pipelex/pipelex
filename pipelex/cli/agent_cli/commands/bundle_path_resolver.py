"""Shared path→bundle resolution for agent CLI bundle commands.

``validate bundle`` and ``fix bundle`` must resolve the user's ``path`` argument identically —
fix must patch exactly the file validate judged. One helper owns the resolution: a ``.mthds``
file is taken as-is; a directory auto-detects the default bundle file name (or a single
``*.mthds``), errors loudly on ambiguity, and injects itself into the library dirs (making it
part of the per-call write scope). Adoption by ``run bundle`` / ``inputs bundle`` is a
follow-up.
"""

from pathlib import Path

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def resolve_bundle_target(path: str, *, library_dir: list[str] | None) -> tuple[str, list[str] | None]:
    """Resolve a ``path`` CLI argument into ``(bundle_path, library_dir)``.

    Directory mode auto-detects the bundle file — ``DEFAULT_BUNDLE_FILE_NAME`` if present, else
    a single ``*.mthds`` — and prepends the directory itself to ``library_dir`` so sibling
    files load (and, being user-passed, fall inside the fix write scope). No file / multiple
    ambiguous files / not-a-``.mthds`` path exit 2 via ``agent_error`` (no verdict produced).

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a bundle directory).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.

    Returns:
        ``(bundle_path, library_dir)`` — the resolved bundle file path, and the possibly
        directory-augmented library dirs (``None`` when none apply).
    """
    target_path = Path(path)

    if target_path.is_dir():
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                agent_error(f"No .mthds bundle file found in directory '{path}'", error_type="FileNotFoundError", exit_code=2)
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                agent_error(
                    f"Multiple .mthds files found in '{path}' ({mthds_names}) and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly instead.",
                    error_type="ArgumentError",
                    exit_code=2,
                )
            bundle_path = str(mthds_files[0])

        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]
        return bundle_path, library_dir

    if is_pipelex_file(target_path):
        return path, library_dir

    agent_error(
        f"'{path}' is not a .mthds file or directory. "
        f"Use 'validate pipe <code>' for pipe codes, or 'validate bundle <path>' for .mthds files/directories.",
        error_type="ArgumentError",
        exit_code=2,
    )
