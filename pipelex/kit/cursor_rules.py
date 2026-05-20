from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import typer
import yaml

from pipelex.kit.exceptions import KitError
from pipelex.kit.index_models import KitIndex
from pipelex.kit.paths import get_kit_agents_dir
from pipelex.types import Traversable

# Marker written into the YAML front-matter of every Pipelex-generated .mdc file so the
# cleanup path can identify and remove stale files even after their source markdown has
# been removed from `pipelex/kit/agent_rules/`.
_PIPELEX_MARKER_KEY = "pipelex_managed"


def _iter_agent_files(agents_dir: Traversable) -> Iterable[tuple[str, str]]:
    """Iterate over agent markdown files.

    Args:
        agents_dir: Traversable pointing to agents directory

    Yields:
        Tuples of (filename, file_content)
    """
    for child in agents_dir.iterdir():
        if child.name.endswith(".md") and child.is_file():
            yield child.name, child.read_text(encoding="utf-8")


def _front_matter_for(name: str, kit_index: KitIndex) -> dict[str, Any]:
    """Build front-matter for a specific file.

    Args:
        name: Filename (e.g., "pytest_standards.md")
        kit_index: Kit index configuration

    Returns:
        Merged front-matter dictionary
    """
    base = kit_index.agent_rules.cursor.front_matter.copy()
    key = name.removesuffix(".md")
    if key in kit_index.agent_rules.cursor.files:
        base |= kit_index.agent_rules.cursor.files[key].front_matter
    # Remove globs if it's an empty list
    if "globs" in base and base["globs"] == []:
        del base["globs"]
    base[_PIPELEX_MARKER_KEY] = True
    return base


def _is_pipelex_managed(mdc_path: Path) -> bool:
    """Return True if the .mdc file's YAML front-matter carries the Pipelex marker."""
    try:
        text = mdc_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end == -1:
        return False
    block = text[4:end]
    try:
        parsed: Any = yaml.safe_load(block)
    except yaml.YAMLError:
        return False
    if not isinstance(parsed, dict):
        return False
    parsed_dict = cast("dict[str, Any]", parsed)
    return parsed_dict.get(_PIPELEX_MARKER_KEY) is True


def update_cursor_rules(repo_root: Path, kit_index: KitIndex, agent_set: str) -> None:
    """Update Cursor .mdc rule files from agent markdown with YAML front-matter.

    Args:
        repo_root: Repository root directory
        kit_index: Kit index configuration
        agent_set: Agent set to limit exported files
    """
    agents_dir = get_kit_agents_dir()
    out_dir = repo_root / ".cursor" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)

    allowed_files: set[str] | None = None
    rules_set = kit_index.agent_rules.sets.get(agent_set)
    if not rules_set:
        msg = f"Agent set '{agent_set}' not found in index.toml. Available sets: {list(kit_index.agent_rules.sets.keys())}"
        raise KitError(msg)
    allowed_files = set(rules_set)

    for fname, body in _iter_agent_files(agents_dir):
        if fname not in allowed_files:
            continue
        fm = _front_matter_for(fname, kit_index)
        yaml_block = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n"
        mdc = yaml_block + body
        out_path = out_dir / (fname.removesuffix(".md") + ".mdc")

        # Only write and print if content changed
        existing_content = out_path.read_text(encoding="utf-8") if out_path.exists() else None
        if existing_content != mdc:
            out_path.write_text(mdc, encoding="utf-8")
            typer.echo(f"✅ Exported {out_path}")
        else:
            typer.echo(f"⚪ Unchanged {out_path}")


def remove_cursor_rules(repo_root: Path) -> None:
    """Remove Pipelex-generated Cursor .mdc files.

    Scans every .mdc file in `.cursor/rules/` and deletes the file when either:
    - its YAML front-matter carries the Pipelex marker (`pipelex_managed: true`), or
    - its stem matches a currently-known agent_rules source file (backward compat for
      files generated before the marker was introduced).

    Args:
        repo_root: Repository root directory
    """
    agents_dir = get_kit_agents_dir()
    out_dir = repo_root / ".cursor" / "rules"

    if not out_dir.exists():
        typer.echo(f"⚠️  Directory {out_dir} does not exist - nothing to remove")
        return

    current_stems = {fname.removesuffix(".md") for fname, _ in _iter_agent_files(agents_dir)}

    removed_count = 0
    for mdc_path in sorted(out_dir.glob("*.mdc")):
        if not mdc_path.is_file():
            continue
        if _is_pipelex_managed(mdc_path) or mdc_path.stem in current_stems:
            mdc_path.unlink()
            typer.echo(f"🗑️  Deleted {mdc_path}")
            removed_count += 1

    if removed_count == 0:
        typer.echo("⚠️  No Cursor rules found to remove")
