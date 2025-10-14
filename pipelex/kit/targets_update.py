import difflib
import re
from importlib.abc import Traversable
from pathlib import Path

import typer

from pipelex.kit.index_models import KitIndex, Target
from pipelex.kit.markers import find_span, replace_span, wrap
from pipelex.kit.paths import get_agents_dir


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


# TODO: fix bug which makes it not idempotent (because heading 1 gets deleted)
def build_merged_rules(idx: KitIndex, agent_set: str | None = None) -> str:
    """Build merged agent documentation from ordered files.

    Args:
        idx: Kit index configuration
        agent_set: Name of the agent set to use (defaults to idx.agents.default_set)

    Returns:
        Merged markdown content with demoted headings
    """
    agents_dir = get_agents_dir()

    if agent_set is None:
        agent_set = idx.agent_rules.default_set

    if agent_set not in idx.agent_rules.sets:
        msg = f"Agent set '{agent_set}' not found in index.toml. Available sets: {list(idx.agent_rules.sets.keys())}"
        raise ValueError(msg)

    parts: list[str] = []

    for name in idx.agent_rules.sets[agent_set]:
        md = _read_agent_file(agents_dir, name)
        demoted = _demote_headings(md, idx.agent_rules.demote)
        parts.append(demoted.rstrip())

    return ("\n\n".join(parts)).strip() + "\n"


def _insert_block_with_markers(target_md: str, block_md: str, main_title: str | None, markers: tuple[str, str]) -> str:
    """Insert block into target markdown using marker-based logic.

    Args:
        target_md: Existing target markdown content
        block_md: Block to insert
        main_title: Main title (H1) to add inside markers when inserting into empty file or file with no H1 headings
        markers: Tuple of (begin_marker, end_marker)

    Returns:
        Updated markdown with block inserted and markers added
    """
    marker_begin, marker_end = markers

    # Check if file is empty or has no H1 heading
    is_empty = not target_md or not target_md.strip()
    h1_pattern = r"^#\s+.+$"
    has_h1 = bool(target_md) and bool(re.search(h1_pattern, target_md, flags=re.MULTILINE))

    # If empty or no H1 heading, add main_title INSIDE the markers
    if (is_empty or not has_h1) and main_title:
        content_with_heading = f"{main_title}\n\n{block_md}"
        wrapped_block = wrap(marker_begin, marker_end, content_with_heading)
    else:
        # File already has H1 heading, don't add another one
        wrapped_block = wrap(marker_begin, marker_end, block_md)

    # Append at the end
    if is_empty:
        return wrapped_block + "\n"
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
    targets: dict[str, Target],
    dry_run: bool,
    diff: bool,
    backup: str | None,
) -> None:
    """Update target files with merged agent documentation.

    Args:
        repo_root: Repository root directory
        merged_rules: Merged markdown content to insert
        targets: Dictionary of target file configurations keyed by ID
        dry_run: If True, only print what would be done
        diff: If True, show unified diff
        backup: Backup suffix (e.g., ".bak"), or None for no backup
    """
    for target in targets.values():
        target_path = repo_root / target.path
        before = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        span = find_span(before, target.marker_begin, target.marker_end)

        if span:
            # Markers exist - replace content between them
            wrapped_block = wrap(target.marker_begin, target.marker_end, merged_rules)
            after = replace_span(before, span, wrapped_block)
        else:
            # No markers - insert with markers
            after = _insert_block_with_markers(
                before,
                merged_rules,
                target.heading_1,
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


def remove_from_targets(
    repo_root: Path,
    targets: dict[str, Target],
    delete_files: bool,
    dry_run: bool,
    diff: bool,
    backup: str | None,
) -> None:
    """Remove agent documentation from target files.

    Args:
        repo_root: Repository root directory
        targets: Dictionary of target file configurations keyed by ID
        delete_files: If True, delete entire files; if False, only remove marked sections
        dry_run: If True, only print what would be done
        diff: If True, show unified diff
        backup: Backup suffix (e.g., ".bak"), or None for no backup
    """
    for target in targets.values():
        target_path = repo_root / target.path

        if not target_path.exists():
            typer.echo(f"⚠️  File {target_path} does not exist - skipping")
            continue

        if delete_files:
            # Delete the entire file
            if dry_run:
                typer.echo(f"[DRY] delete {target_path}")
            else:
                if backup:
                    backup_path = target_path.with_suffix(target_path.suffix + backup)
                    target_path.rename(backup_path)
                    typer.echo(f"📦 Backup saved to {backup_path}")
                else:
                    target_path.unlink()
                typer.echo(f"🗑️  Deleted {target_path}")
        else:
            # Remove only the marked section
            before = target_path.read_text(encoding="utf-8")
            span = find_span(before, target.marker_begin, target.marker_end)

            if not span:
                typer.echo(f"⚠️  No marked section found in {target_path} - skipping")
                continue

            # Remove the marked section entirely
            before_section = before[: span[0]].rstrip()
            after_section = before[span[1] :].lstrip()

            # If there's content before or after, join them
            if before_section and after_section:
                after = before_section + "\n\n" + after_section
            elif before_section:
                after = before_section + "\n"
            elif after_section:
                after = after_section
            else:
                # File only contained the marked section - delete the file
                if dry_run:
                    typer.echo(f"[DRY] delete {target_path} (file only contained marked section)")
                else:
                    if backup:
                        backup_path = target_path.with_suffix(target_path.suffix + backup)
                        target_path.rename(backup_path)
                        typer.echo(f"📦 Backup saved to {backup_path}")
                    else:
                        target_path.unlink()
                    typer.echo(f"🗑️  Deleted {target_path} (file only contained marked section)")
                continue

            if dry_run:
                typer.echo(f"[DRY] remove marked section from {target_path}")
                if diff:
                    diff_output = _diff(before, after, str(target_path))
                    if diff_output:
                        typer.echo(diff_output)
            else:
                if backup:
                    backup_path = target_path.with_suffix(target_path.suffix + backup)
                    backup_path.write_text(before, encoding="utf-8")
                    typer.echo(f"📦 Backup saved to {backup_path}")

                target_path.write_text(after, encoding="utf-8")
                typer.echo(f"✅ Removed marked section from {target_path}")

                if diff:
                    diff_output = _diff(before, after, str(target_path))
                    if diff_output:
                        typer.echo(diff_output)
