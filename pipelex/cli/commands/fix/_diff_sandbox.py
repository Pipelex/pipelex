"""Temp-copy sandbox for the ``pipelex fix bundle --diff`` preview.

The fix loop has no no-write mode and re-validation loads from disk, so an honest preview
runs the REAL loop against copies: the entry file and each **explicit** ``-L`` dir are
mirrored into a scratch dir, ``library_dirs`` is remapped to the copies, and the loop runs
there — originals untouched. Ambient-resolved dirs (``library_dirs is None``) are not copied:
they are read-only under the loop's write-scope rule in the real run too, and being absolute
they load identically from the sandbox run.

Layout subtlety: when the entry file lies under one of the explicit ``-L`` dirs (directory
mode always does this), the sandbox entry path must be the file *inside* the mirrored dir
copy — a separate entry copy would make the loop validate one copy while the library loads
another, declaring every pipe twice.
"""

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class PreviewSandbox(NamedTuple):
    """The mirrored bundle a ``--diff`` preview runs against, plus the copy→original mapping."""

    entry_path: Path
    """The sandbox path of the entry bundle file (resolved)."""
    library_dirs: list[Path] | None
    """``library_dirs`` remapped onto the sandbox copies (``None``/``[]`` pass through)."""
    dir_mappings: list[tuple[Path, Path]]
    """``(copy_root, original_root)`` per explicit ``-L`` dir, both resolved."""
    entry_mapping: tuple[Path, Path]
    """``(entry_copy, entry_original)``, both resolved."""

    def to_original(self, path_str: str) -> str:
        """Map a sandbox file path back to the original it mirrors.

        Paths outside the sandbox (ambient-resolved files) pass through resolved-as-is.
        """
        resolved = Path(path_str).resolve()
        entry_copy, entry_original = self.entry_mapping
        if resolved == entry_copy:
            return str(entry_original)
        for copy_root, original_root in self.dir_mappings:
            if resolved.is_relative_to(copy_root):
                return str(original_root / resolved.relative_to(copy_root))
        return str(resolved)


def mirror_bundle_for_preview(
    entry_path: Path,
    *,
    library_dirs: Sequence[Path] | None,
    sandbox_root: Path,
) -> PreviewSandbox:
    """Mirror the entry file and each explicit ``-L`` dir into ``sandbox_root``.

    Each explicit dir is copied wholesale (the loader may read more than ``.mthds`` files),
    preserving its internal layout under ``sandbox_root/lib_<i>``. The entry file resolves to
    its in-copy location when it lives under one of the dirs, else to a standalone copy under
    ``sandbox_root/entry``. ``library_dirs=None`` (ambient resolution) and an explicit ``[]``
    (genuinely single-file) pass through unchanged so the sandbox run keeps the same
    single-file / write-scope semantics as the real run.
    """
    entry_resolved = entry_path.resolve()
    dir_mappings: list[tuple[Path, Path]] = []
    remapped_dirs: list[Path] | None = None
    entry_copy: Path | None = None

    if library_dirs is not None:
        remapped_dirs = []
        for dir_index, library_dir in enumerate(library_dirs):
            original_root = Path(library_dir).resolve()
            copy_root = (sandbox_root / f"lib_{dir_index}").resolve()
            shutil.copytree(original_root, copy_root)
            dir_mappings.append((copy_root, original_root))
            remapped_dirs.append(copy_root)
            if entry_copy is None and entry_resolved.is_relative_to(original_root):
                entry_copy = copy_root / entry_resolved.relative_to(original_root)

    if entry_copy is None:
        entry_dir = sandbox_root / "entry"
        entry_dir.mkdir(parents=True, exist_ok=True)
        entry_copy = (entry_dir / entry_resolved.name).resolve()
        shutil.copy2(entry_resolved, entry_copy)

    return PreviewSandbox(
        entry_path=entry_copy,
        library_dirs=remapped_dirs,
        dir_mappings=dir_mappings,
        entry_mapping=(entry_copy, entry_resolved),
    )
