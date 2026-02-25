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
    from collections.abc import Set as AbstractSet

    from pipelex.tools.misc.pretty import PrettyPrintable


def has_diff_dirs(
    dir1: str | Path,
    dir2: str | Path,
    exclude_files: AbstractSet[str] | None = None,
    exclude_dirs: AbstractSet[str] | None = None,
) -> bool:
    """Check if there are any differences between two directories.

    Args:
        dir1: First directory path.
        dir2: Second directory path.
        exclude_files: Set of file names to exclude from comparison (e.g., {"pipelex_service.toml"}).
        exclude_dirs: Set of directory names to exclude from comparison (e.g., {"storage"}).

    Returns:
        True if there are any files only in left, only in right, or different files.
    """
    dir1 = Path(dir1)
    dir2 = Path(dir2)
    exclude_files = exclude_files or set()
    exclude_dirs = exclude_dirs or set()

    def _filter_excluded_files(file_list: list[str]) -> list[str]:
        return [file for file in file_list if file not in exclude_files]

    def _has_diff(dir_comparison: filecmp.dircmp[str]) -> bool:
        # Filter out excluded directories from left_only and right_only
        left_only_filtered = _filter_excluded_files([item for item in dir_comparison.left_only if item not in exclude_dirs])
        right_only_filtered = _filter_excluded_files([item for item in dir_comparison.right_only if item not in exclude_dirs])
        if left_only_filtered or right_only_filtered:
            return True

        # Check for different files using shallow comparison (excluding excluded files)
        diff_files_filtered = _filter_excluded_files(dir_comparison.diff_files)
        if diff_files_filtered:
            return True

        # Force deep comparison for common files that passed shallow comparison
        # This is needed because shallow comparison only checks metadata (size, mtime)
        common_files_filtered = _filter_excluded_files(dir_comparison.common_files)
        if common_files_filtered:
            _, mismatch, errors = filecmp.cmpfiles(
                dir_comparison.left,
                dir_comparison.right,
                common_files_filtered,
                shallow=False,  # Force byte-by-byte comparison
            )
            if mismatch or errors:
                return True

        # Check subdirectories recursively (excluding excluded directories)
        filtered_subdirs = {name: sub for name, sub in dir_comparison.subdirs.items() if name not in exclude_dirs}
        return any(_has_diff(sub) for sub in filtered_subdirs.values())

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


# TODO: improve using toml reader/writer?
def _generate_diff_summary(diff_content: str, left_is_newer: bool) -> str | None:
    """Generate a concise summary of what changes would be applied to sync files.

    Parses unified diff content and generates a human-readable summary explaining
    what changes would be needed to update the obsolete version to match the newer one.

    Args:
        diff_content: The unified diff string
        left_is_newer: True if left file is newer, False if right is newer

    Returns:
        A concise summary string, or None if the diff is too complex to summarize
    """
    lines = diff_content.split("\n")

    # Skip header lines (---, +++, @@)
    change_lines = [line for line in lines if line and line[0] in {"+", "-"} and not line.startswith(("---", "+++"))]

    if not change_lines:
        return None

    # Collect additions and removals
    in_left_only: list[str] = []  # Lines present in left but not in right (marked with -)
    in_right_only: list[str] = []  # Lines present in right but not in left (marked with +)

    for line in change_lines:
        if line.startswith("-"):
            in_left_only.append(line[1:].strip())
        elif line.startswith("+"):
            in_right_only.append(line[1:].strip())

    # Determine what action to describe based on which side is newer
    # We always describe changes from the OBSOLETE version to the NEWER version
    # The obsolete version is what needs to be updated

    if left_is_newer:
        # Left is newer (source of truth), right is obsolete (needs updating)
        # Right currently has: in_right_only
        # Right needs to have: in_left_only
        obsolete_current_value = in_right_only  # What the obsolete version currently has
        newer_target_value = in_left_only  # What the obsolete version should have
        obsolete_location = "right"
    else:
        # Right is newer (source of truth), left is obsolete (needs updating)
        # Left currently has: in_left_only
        # Left needs to have: in_right_only
        obsolete_current_value = in_left_only  # What the obsolete version currently has
        newer_target_value = in_right_only  # What the obsolete version should have
        obsolete_location = "left"

    # Try to identify simple patterns
    # We describe changes FROM obsolete_current_value TO newer_target_value
    if len(newer_target_value) == 1 and len(obsolete_current_value) == 1:
        # Simple modification case
        new_value = newer_target_value[0]
        old_value = obsolete_current_value[0]

        # Try to extract field name and values for key=value patterns
        if "=" in new_value and "=" in old_value:
            new_parts = new_value.split("=", 1)
            old_parts = old_value.split("=", 1)

            if len(new_parts) == 2 and len(old_parts) == 2:
                new_key = new_parts[0].strip()
                old_key = old_parts[0].strip()

                if new_key == old_key:
                    # Same field, different values - describe change from old to new
                    new_val = new_parts[1].strip()
                    old_val = old_parts[1].strip()
                    # Strip inline comments for clarity (e.g., "value  # comment" -> "value")
                    if "#" in new_val:
                        new_val = new_val.split("#")[0].strip()
                    if "#" in old_val:
                        old_val = old_val.split("#")[0].strip()
                    return f"  Sync would change {new_key} from {old_val} to {new_val} in {obsolete_location}"

        # Generic modification
        return f"  Sync would replace '{old_value}' with '{new_value}' in {obsolete_location}"

    elif len(newer_target_value) > 0 and len(obsolete_current_value) == 0:
        # Obsolete version is missing these lines - need to add them
        if len(newer_target_value) == 1:
            new_value = newer_target_value[0]
            # Try to extract field name
            if "=" in new_value:
                field = new_value.split("=", 1)[0].strip()
                return f"  Sync would add {field} to {obsolete_location}"
            return f"  Sync would add line '{new_value}' to {obsolete_location}"
        else:
            return f"  Sync would add {len(newer_target_value)} line(s) to {obsolete_location}"

    elif len(newer_target_value) == 0 and len(obsolete_current_value) > 0:
        # Obsolete version has extra lines that shouldn't be there - need to remove them
        if len(obsolete_current_value) == 1:
            old_value = obsolete_current_value[0]
            # Try to extract field name
            if "=" in old_value:
                field = old_value.split("=", 1)[0].strip()
                return f"  Sync would remove {field} from {obsolete_location}"
            return f"  Sync would remove line '{old_value}' from {obsolete_location}"
        else:
            return f"  Sync would remove {len(obsolete_current_value)} line(s) from {obsolete_location}"

    else:
        # Complex change with multiple additions and removals
        summary_parts: list[str] = []
        if newer_target_value:
            summary_parts.append(f"add {len(newer_target_value)} line(s)")
        if obsolete_current_value:
            summary_parts.append(f"remove {len(obsolete_current_value)} line(s)")
        return f"  Sync would {' and '.join(summary_parts)} in {obsolete_location}"


def make_diff_dirs_pretty(
    dir1: str | Path,
    dir2: str | Path,
    exclude_files: AbstractSet[str] | None = None,
    exclude_dirs: AbstractSet[str] | None = None,
) -> PrettyPrintable:
    """Generate a PrettyPrintable representation of directory differences.

    Args:
        dir1: First directory path.
        dir2: Second directory path.
        exclude_files: Set of file names to exclude from comparison (e.g., {"pipelex_service.toml"}).
        exclude_dirs: Set of directory names to exclude from comparison (e.g., {"storage"}).

    Returns:
        A Rich renderable showing files only in left, only in right,
        and different files with full diff content. For different files, indicates
        which version is newer based on modification time.
    """
    dir1 = Path(dir1)
    dir2 = Path(dir2)
    exclude_files = exclude_files or set()
    exclude_dirs = exclude_dirs or set()

    sections: list[PrettyPrintable] = []

    def _filter_excluded_files(file_list: list[str]) -> list[str]:
        return [file for file in file_list if file not in exclude_files]

    def _collect_diffs(dir_comparison: filecmp.dircmp[str], relative_path: str = "") -> None:
        # Files only in left directory (excluding excluded files and directories)
        left_only_filtered = _filter_excluded_files([item for item in dir_comparison.left_only if item not in exclude_dirs])
        if left_only_filtered:
            table = Table(
                title=f"[yellow]Only in {dir_comparison.left}[/yellow]",
                show_header=False,
                show_edge=True,
                border_style="yellow",
                padding=(0, 1),
            )
            table.add_column("File", style="yellow")
            for name in sorted(left_only_filtered):
                full_path = Path(relative_path, name) if relative_path else Path(name)
                table.add_row(str(full_path))
            sections.append(table)

        # Files only in right directory (excluding excluded files and directories)
        right_only_filtered = _filter_excluded_files([item for item in dir_comparison.right_only if item not in exclude_dirs])
        if right_only_filtered:
            table = Table(
                title=f"[cyan]Only in {dir_comparison.right}[/cyan]",
                show_header=False,
                show_edge=True,
                border_style="cyan",
                padding=(0, 1),
            )
            table.add_column("File", style="cyan")
            for name in sorted(right_only_filtered):
                full_path = Path(relative_path, name) if relative_path else Path(name)
                table.add_row(str(full_path))
            sections.append(table)

        # Different files - combine shallow diff_files with deep comparison of common_files
        # This is needed because diff_files only contains files that failed shallow comparison
        # Apply exclusion filter to diff_files
        different_files = set(_filter_excluded_files(dir_comparison.diff_files))

        # Force deep comparison for common files (excluding excluded files)
        common_files_filtered = _filter_excluded_files(dir_comparison.common_files)
        if common_files_filtered:
            _, mismatch, errors = filecmp.cmpfiles(
                dir_comparison.left,
                dir_comparison.right,
                common_files_filtered,
                shallow=False,  # Force byte-by-byte comparison
            )
            different_files.update(mismatch)
            different_files.update(errors)

        for name in sorted(different_files):
            p1 = Path(dir_comparison.left, name)
            p2 = Path(dir_comparison.right, name)
            full_path = Path(relative_path, name) if relative_path else Path(name)

            # Get modification times
            mtime1 = p1.stat().st_mtime
            mtime2 = p2.stat().st_mtime

            # Determine update direction
            left_is_newer = mtime1 > mtime2
            if left_is_newer:
                direction_indicator = " [green](left is newer)[/green]"
            elif mtime2 > mtime1:
                direction_indicator = " [blue](right is newer)[/blue]"
            else:
                direction_indicator = " [dim](same modification time)[/dim]"
                left_is_newer = True  # Default to treating left as newer if times are equal

            title_text = Text.from_markup(f"[bold magenta]Diff: {full_path}[/bold magenta]{direction_indicator}")
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
                    # Parse the diff to provide a summary
                    summary = _generate_diff_summary(diff_content, left_is_newer)
                    if summary:
                        summary_text = Text(summary, style="dim yellow")
                        sections.append(summary_text)

                    diff_syntax = Syntax(diff_content, "diff", theme="monokai", line_numbers=False)
                    sections.append(diff_syntax)
                else:
                    sections.append(Text("(no content differences)", style="dim"))
            except UnicodeDecodeError:
                binary_note = Text("(binary or non-text file; cannot show diff)", style="dim red")
                sections.append(binary_note)

        # Recurse into subdirectories (excluding excluded directories)
        for subdir_name, sub in sorted(dir_comparison.subdirs.items()):
            if subdir_name in exclude_dirs:
                continue
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
