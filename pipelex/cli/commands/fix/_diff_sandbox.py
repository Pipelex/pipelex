"""Temp-copy sandbox for the ``pipelex fix bundle --diff`` preview.

The fix loop has no no-write mode and re-validation loads from disk, so an honest preview
runs the REAL loop against copies. The effective load scope (explicit ``-L`` dirs or ambient
resolution) is canonicalized by resolved identity, mirrored once, and passed separately from
the writable subset. This keeps ambient libraries read-only while ensuring the entry and every
library declaration have the same identity in preview and write mode.

Layout subtlety: when the entry file lies under one of the explicit ``-L`` dirs (directory
mode always does this), the sandbox entry path must be the file *inside* the mirrored dir
copy — a separate entry copy would make the loop validate one copy while the library loads
another, declaring every pipe twice.
"""

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from pipelex.config import get_config
from pipelex.hub import resolve_library_dirs


def _excluded_copy_entries(  # kw-only: ignore - shutil.copytree invokes ignore callbacks positionally
    directory: str,
    names: list[str],
) -> set[str]:
    """Return directory entries excluded by the real library scanners.

    ``copytree`` otherwise mirrors virtualenvs, VCS data, caches, and result trees that the
    loader never reads. Symlink entries are not traversed here; ``copytree(symlinks=True)``
    preserves them as links instead of copying data from outside the requested root.
    """
    excluded_entries: set[str] = set()
    excluded_dirs = get_config().pipelex.scan_config.excluded_dirs
    current_dir = Path(directory)
    for name in names:
        candidate = current_dir / name
        if not candidate.is_dir():
            continue
        for excluded_dir in excluded_dirs:
            excluded_path = Path(excluded_dir)
            if excluded_path.is_absolute():
                if candidate.resolve().is_relative_to(excluded_path.resolve()):
                    excluded_entries.add(name)
                    break
            elif name == excluded_dir:
                excluded_entries.add(name)
                break
    return excluded_entries


class PreviewSandbox(NamedTuple):
    """The mirrored bundle a ``--diff`` preview runs against, plus the copy→original mapping."""

    entry_path: Path
    """The sandbox path of the entry bundle file (resolved)."""
    library_dirs: list[Path]
    """The complete effective load scope remapped onto canonical sandbox copies."""
    writable_library_dirs: list[Path]
    """The subset of copied library dirs the real invocation authorized for writes."""
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

    Each effective dir is copied with the loader's configured directory exclusions (the loader
    may read Python files as well as ``.mthds`` files), preserving its internal layout under
    ``sandbox_root/lib_<i>``. Symlinks are preserved rather than dereferenced. The entry file resolves to
    its in-copy location when it lives under one of the dirs, else to a standalone copy under
    ``sandbox_root/entry``. Equivalent and overlapping roots collapse to one canonical copy;
    ambient copies are part of load scope but excluded from ``writable_library_dirs``.
    """
    entry_resolved = entry_path.resolve()
    effective_dirs, _ = resolve_library_dirs(library_dirs)
    unique_roots: list[Path] = []
    for library_dir in effective_dirs:
        resolved_root = Path(library_dir).resolve()
        if resolved_root not in unique_roots:
            unique_roots.append(resolved_root)
    canonical_roots = [root for root in unique_roots if not any(root != other and root.is_relative_to(other) for other in unique_roots)]
    dir_mappings: list[tuple[Path, Path]] = []
    remapped_dirs: list[Path] = []
    entry_copy: Path | None = None

    for dir_index, original_root in enumerate(canonical_roots):
        copy_root = (sandbox_root / f"lib_{dir_index}").resolve()
        if original_root.exists():
            shutil.copytree(original_root, copy_root, symlinks=True, ignore=_excluded_copy_entries)
        else:
            # The real loader skips a missing -L dir (it contributes no files) while
            # keeping it in effective_dirs; mirror that as an empty copy so copytree does
            # not crash, is_single_file is preserved, and the preview verdict tracks the run.
            copy_root.mkdir(parents=True, exist_ok=True)
        dir_mappings.append((copy_root, original_root))
        remapped_dirs.append(copy_root)
        if entry_copy is None and entry_resolved.is_relative_to(original_root):
            entry_copy = copy_root / entry_resolved.relative_to(original_root)

    for copy_root, original_root in dir_mappings:
        if not original_root.exists():
            continue
        for original_link in original_root.rglob("*"):
            if not original_link.is_symlink():
                continue
            copied_link = copy_root / original_link.relative_to(original_root)
            resolved_target = original_link.resolve()
            copied_target: Path | None = None
            for target_copy_root, target_original_root in dir_mappings:
                if resolved_target.is_relative_to(target_original_root):
                    copied_target = target_copy_root / resolved_target.relative_to(target_original_root)
                    break
            if copied_target is None:
                continue
            copied_link.unlink()
            copied_link.symlink_to(copied_target, target_is_directory=resolved_target.is_dir())

    if entry_copy is None:
        entry_dir = sandbox_root / "entry"
        entry_dir.mkdir(parents=True, exist_ok=True)
        entry_copy = (entry_dir / entry_resolved.name).resolve()
        shutil.copy2(entry_resolved, entry_copy)
    elif entry_copy.is_symlink() and not entry_copy.resolve().is_relative_to(sandbox_root.resolve()):
        entry_copy.unlink()
        shutil.copy2(entry_resolved, entry_copy)

    return PreviewSandbox(
        entry_path=entry_copy,
        library_dirs=remapped_dirs,
        writable_library_dirs=remapped_dirs if library_dirs is not None else [],
        dir_mappings=dir_mappings,
        entry_mapping=(entry_copy, entry_resolved),
    )
