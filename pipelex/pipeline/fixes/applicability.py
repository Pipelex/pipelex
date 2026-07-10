"""Shared source and write-scope predicates for autofix execution and CLI hints."""

from collections.abc import Sequence
from pathlib import Path

from pipelex.suggested_fix import SuggestedFix


def is_safe_fix_for_load_scope(fix: SuggestedFix, *, is_single_file: bool) -> bool:
    """Whether a safe fix has enough source identity for this load scope."""
    if not fix.safety.is_safe:
        return False
    return fix.source is not None or is_single_file


def is_target_in_write_scope(target_path: Path, *, entry_path: Path, writable_dirs: Sequence[Path]) -> bool:
    """Whether a target is the entry file or lies under an explicitly writable directory."""
    return target_path == entry_path or any(target_path.is_relative_to(writable_dir) for writable_dir in writable_dirs)
