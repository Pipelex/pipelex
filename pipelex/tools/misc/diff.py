from __future__ import annotations

import difflib
import filecmp
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Group
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from pipelex.tools.misc.pretty import PrettyPrinter

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


def has_diff_dirs(dir1: str | Path, dir2: str | Path) -> bool:
    """Check if there are any differences between two directories.

    Returns True if there are any files only in left, only in right, or different files.
    """
    dir1 = Path(dir1)
    dir2 = Path(dir2)

    def _has_diff(dir_comparison: filecmp.dircmp[str]) -> bool:
        # Check for files only in left or right
        if dir_comparison.left_only or dir_comparison.right_only:
            return True

        # Check for different files
        if dir_comparison.diff_files:
            return True

        # Check subdirectories recursively
        return any(_has_diff(sub) for sub in dir_comparison.subdirs.values())

    return _has_diff(filecmp.dircmp(str(dir1), str(dir2)))


def diff_files(path1: str | Path, path2: str | Path) -> str:
    path1 = Path(path1)
    path2 = Path(path2)

    left_lines = path1.read_text(encoding="utf-8").splitlines(keepends=True)
    right_lines = path2.read_text(encoding="utf-8").splitlines(keepends=True)

    diff_iter = difflib.unified_diff(
        left_lines,
        right_lines,
        fromfile=str(path1),
        tofile=str(path2),
        lineterm="",
    )
    return "\n".join(diff_iter)


def make_diff_dirs_pretty(dir1: str | Path, dir2: str | Path) -> PrettyPrintable:
    """Generate a PrettyPrintable representation of directory differences.

    Returns a Rich renderable showing files only in left, only in right,
    and different files with full diff content.
    """
    dir1 = Path(dir1)
    dir2 = Path(dir2)

    sections: list[PrettyPrintable] = []

    def _collect_diffs(dir_comparison: filecmp.dircmp[str], relative_path: str = "") -> None:
        # Files only in left directory
        if dir_comparison.left_only:
            table = Table(
                title=f"[yellow]Only in {dir_comparison.left}[/yellow]",
                show_header=False,
                show_edge=True,
                border_style="yellow",
                padding=(0, 1),
            )
            table.add_column("File", style="yellow")
            for name in sorted(dir_comparison.left_only):
                full_path = Path(relative_path, name) if relative_path else Path(name)
                table.add_row(str(full_path))
            sections.append(table)

        # Files only in right directory
        if dir_comparison.right_only:
            table = Table(
                title=f"[cyan]Only in {dir_comparison.right}[/cyan]",
                show_header=False,
                show_edge=True,
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("File", style="cyan")
            for name in sorted(dir_comparison.right_only):
                full_path = Path(relative_path, name) if relative_path else Path(name)
                table.add_row(str(full_path))
            sections.append(table)

        # Different files
        for name in sorted(dir_comparison.diff_files):
            p1 = Path(dir_comparison.left, name)
            p2 = Path(dir_comparison.right, name)
            full_path = Path(relative_path, name) if relative_path else Path(name)

            title_text = Text(f"Diff: {full_path}", style="bold magenta")
            sections.append(title_text)

            try:
                left_lines = p1.read_text(encoding="utf-8").splitlines(keepends=True)
                right_lines = p2.read_text(encoding="utf-8").splitlines(keepends=True)

                diff_iter = difflib.unified_diff(
                    left_lines,
                    right_lines,
                    fromfile=str(p1),
                    tofile=str(p2),
                    lineterm="",
                )
                diff_content = "\n".join(diff_iter)

                if diff_content:
                    diff_syntax = Syntax(diff_content, "diff", theme="monokai", line_numbers=False)
                    sections.append(diff_syntax)
                else:
                    sections.append(Text("(no content differences)", style="dim"))
            except UnicodeDecodeError:
                binary_note = Text("(binary or non-text file; cannot show diff)", style="dim red")
                sections.append(binary_note)

        # Recurse into subdirectories
        for subdir_name, sub in sorted(dir_comparison.subdirs.items()):
            new_relative_path = str(Path(relative_path, subdir_name)) if relative_path else subdir_name
            _collect_diffs(sub, new_relative_path)

    _collect_diffs(filecmp.dircmp(str(dir1), str(dir2)))

    if not sections:
        return Text("No differences found", style="green")

    return Group(*sections)


def diff_dirs(dir1: str | Path, dir2: str | Path) -> None:
    """Print differences between two directories using PrettyPrinter.

    This function generates a formatted display of all differences including
    files only in left, only in right, and different files with full diff content.
    """
    dir1 = Path(dir1)
    dir2 = Path(dir2)

    pretty_diff = make_diff_dirs_pretty(dir1, dir2)
    PrettyPrinter.pretty_print(
        content=pretty_diff,
        title=f"Directory Diff: {dir1} ↔ {dir2}",
        border_style="bold blue",
    )
