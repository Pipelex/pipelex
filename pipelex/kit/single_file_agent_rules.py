import difflib
import re
from pathlib import Path

import typer

from pipelex.kit.index_models import KitIndex, Target
from pipelex.kit.paths import get_kit_agents_dir
from pipelex.types import Traversable


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


def build_merged_rules(kit_index: KitIndex, agent_set: str | None = None, file_list: list[str] | None = None) -> str:
    """Build merged agent documentation from ordered files.

    Args:
        kit_index: Kit index configuration
        agent_set: Name of the agent set to use (defaults to kit_index.agents.default_set)
        file_list: Optional explicit list of files to merge (overrides agent_set lookup)

    Returns:
        Merged markdown content with demoted headings
    """
    agents_dir = get_kit_agents_dir()

    # If explicit file list provided, use it
    if file_list is not None:
        files_to_merge = file_list
    else:
        # Otherwise, look up the agent set
        if agent_set is None:
            agent_set = kit_index.agent_rules.default_set

        if agent_set not in kit_index.agent_rules.sets:
            msg = f"Agent set '{agent_set}' not found in index.toml. Available sets: {list(kit_index.agent_rules.sets.keys())}"
            raise ValueError(msg)

        files_to_merge = kit_index.agent_rules.sets[agent_set]

    parts: list[str] = []

    for name in files_to_merge:
        md_content = _read_agent_file(agents_dir, name)
        demoted = _demote_headings(md_content, kit_index.agent_rules.demote)
        parts.append(demoted.rstrip())

    return ("\n\n".join(parts)).strip() + "\n"


def unified_diff(before: str, after: str, path: str) -> str:
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


def update_single_file_agent_rules(
    repo_root: Path,
    kit_index: KitIndex,
    agent_set: str,
    targets: dict[str, Target],
) -> None:
    """Update single-file agent rules targets with merged agent documentation.

    Args:
        repo_root: Repository root directory
        kit_index: Kit index configuration
        agent_set: Default agent set to use (can be overridden by target.sets)
        targets: Dictionary of target file configurations keyed by ID
    """
    for target in targets.values():
        # Check if this target has its own set override for the given agent_set
        target_file_list: list[str] | None = None
        if target.sets and agent_set in target.sets:
            target_file_list = target.sets[agent_set]

        # Build merged rules for this specific target (with override if applicable)
        merged_rules = build_merged_rules(kit_index, agent_set=agent_set, file_list=target_file_list)

        # Add heading
        after = f"# Pipelex Coding Rules\n\n{merged_rules}"

        target_path = repo_root / target.path
        before = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        if before != after:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(after, encoding="utf-8")
            typer.echo(f"✅ Updated {target_path}")
        else:
            typer.echo(f"⚪ Unchanged {target_path}")


def remove_from_targets(
    repo_root: Path,
    targets: dict[str, Target],
) -> None:
    """Remove agent rule files.

    Args:
        repo_root: Repository root directory
        targets: Dictionary of target file configurations keyed by ID
    """
    for target in targets.values():
        target_path = repo_root / target.path

        if not target_path.exists():
            typer.echo(f"⚠️  File {target_path} does not exist - skipping")
            continue

        target_path.unlink()
        typer.echo(f"🗑️  Deleted {target_path}")
