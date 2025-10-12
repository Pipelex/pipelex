"""Build and update merged agent documentation in target files."""

import difflib
import re
from importlib.abc import Traversable
from pathlib import Path

import typer

from pipelex.kit.index_models import KitIndex, Target
from pipelex.kit.markers import find_span, replace_span, wrap


def _read_agent_file(agents_dir: Traversable, name: str) -> str:
    """Read an agent markdown file.

    Args:
        agents_dir: Traversable pointing to agents directory
        name: Filename to read

    Returns:
        File content as string
    """
    return (agents_dir / name).read_text(encoding="utf-8")


def _demote_headings(md_content: str, levels: int) -> str:
    """Demote all headings in markdown content by specified levels.

    Args:
        md_content: Markdown content
        levels: Number of levels to demote

    Returns:
        Markdown with demoted headings
    """
    if levels == 0:
        return md_content

    # Use regex to add extra # to ATX-style headings
    def demote_match(match: re.Match[str]) -> str:
        hashes = match.group(1)
        rest = match.group(2)
        return f"{'#' * levels}{hashes}{rest}"

    # Match lines starting with # (ATX-style headings)
    pattern = r"^(#{1,6})(.*)$"
    return re.sub(pattern, demote_match, md_content, flags=re.MULTILINE)


def build_merged_rules(agents_dir: Traversable, idx: KitIndex) -> str:
    """Build merged agent documentation from ordered files.

    Args:
        agents_dir: Traversable pointing to agents directory
        idx: Kit index configuration

    Returns:
        Merged markdown content with demoted headings
    """
    parts: list[str] = []

    for name in idx.agents.order:
        md = _read_agent_file(agents_dir, name)
        demoted = _demote_headings(md, idx.agents.demote)
        parts.append(demoted.rstrip())

    return ("\n\n".join(parts)).strip() + "\n"


def _insert_block_with_ast(target_md: str, block_md: str, parent: str | None, markers: tuple[str, str]) -> str:
    """Insert block into target markdown with heuristic placement.

    Args:
        target_md: Existing target markdown content
        block_md: Block to insert
        parent: Parent heading to insert under (if specified)
        markers: Tuple of (begin_marker, end_marker)

    Returns:
        Updated markdown with block inserted and markers added
    """
    marker_begin, marker_end = markers
    wrapped_block = wrap(marker_begin, marker_end, block_md)

    if not target_md:
        # Empty file - just insert the wrapped block
        return wrapped_block + "\n"

    # If parent heading is specified, try to find it and insert after
    if parent:
        # Escape special regex characters in parent
        escaped_parent = re.escape(parent.strip())
        # Look for the parent heading line
        pattern = rf"^({escaped_parent})\s*$"
        match = re.search(pattern, target_md, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            # Insert after the parent heading line
            insert_pos = match.end()
            return target_md[:insert_pos] + "\n\n" + wrapped_block + "\n" + target_md[insert_pos:]

    # Fallback: insert after first H1 heading
    h1_pattern = r"^#\s+.+$"
    match = re.search(h1_pattern, target_md, flags=re.MULTILINE)
    if match:
        insert_pos = match.end()
        return target_md[:insert_pos] + "\n\n" + wrapped_block + "\n" + target_md[insert_pos:]

    # Last resort: append at the end
    return target_md.rstrip() + "\n\n" + wrapped_block + "\n"


def _diff(before: str, after: str, path: str) -> str:
    """Generate unified diff between before and after.

    Args:
        before: Original content
        after: Modified content
        path: File path for diff header

    Returns:
        Unified diff string
    """
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def update_targets(
    repo_root: Path,
    merged_rules: str,
    targets: list[Target],
    dry_run: bool,
    diff: bool,
    backup: str | None,
) -> None:
    """Update target files with merged agent documentation.

    Args:
        repo_root: Repository root directory
        merged_rules: Merged markdown content to insert
        targets: List of target file configurations
        dry_run: If True, only print what would be done
        diff: If True, show unified diff
        backup: Backup suffix (e.g., ".bak"), or None for no backup
    """
    for target in targets:
        target_path = repo_root / target.path
        before = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        span = find_span(before, target.marker_begin, target.marker_end)

        if span:
            # Markers exist - replace content between them
            wrapped_block = wrap(target.marker_begin, target.marker_end, merged_rules)
            after = replace_span(before, span, wrapped_block)
        else:
            # No markers - insert via AST and add markers
            after = _insert_block_with_ast(
                before,
                merged_rules,
                target.parent,
                (target.marker_begin, target.marker_end),
            )

        if dry_run:
            typer.echo(f"[DRY] update {target_path}")
            if diff:
                diff_output = _diff(before, after, str(target_path))
                if diff_output:
                    typer.echo(diff_output)
        else:
            if backup and target_path.exists():
                backup_path = target_path.with_suffix(target_path.suffix + backup)
                backup_path.write_text(before, encoding="utf-8")
                typer.echo(f"📦 Backup saved to {backup_path}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(after, encoding="utf-8")
            typer.echo(f"✅ Updated {target_path}")

            if diff:
                diff_output = _diff(before, after, str(target_path))
                if diff_output:
                    typer.echo(diff_output)
