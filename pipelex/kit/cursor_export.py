from collections.abc import Iterable
from importlib.abc import Traversable
from pathlib import Path
from typing import Any

import typer
import yaml

from pipelex.kit.index_models import KitIndex
from pipelex.kit.paths import get_agents_dir


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


def _front_matter_for(name: str, idx: KitIndex) -> dict[str, Any]:
    """Build front-matter for a specific file.

    Args:
        name: Filename (e.g., "pytest_standards.md")
        idx: Kit index configuration

    Returns:
        Merged front-matter dictionary
    """
    base = idx.agent_rules.cursor.front_matter.copy()
    key = name.removesuffix(".md")
    if key in idx.agent_rules.cursor.files:
        base |= idx.agent_rules.cursor.files[key].front_matter
    # Remove globs if it's an empty list
    if "globs" in base and base["globs"] == []:
        del base["globs"]
    return base


def export_cursor_rules(repo_root: Path, idx: KitIndex, dry_run: bool = False) -> None:
    """Export agent markdown files to Cursor .mdc files with YAML front-matter.

    Args:
        repo_root: Repository root directory
        idx: Kit index configuration
        dry_run: If True, only print what would be done
    """
    agents_dir = get_agents_dir()
    out_dir = repo_root / ".cursor" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)

    for fname, body in _iter_agent_files(agents_dir):
        fm = _front_matter_for(fname, idx)
        yaml_block = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n"
        mdc = yaml_block + body
        out_path = out_dir / (fname.removesuffix(".md") + ".mdc")

        if dry_run:
            typer.echo(f"[DRY] write {out_path}")
        else:
            out_path.write_text(mdc, encoding="utf-8")
            typer.echo(f"✅ Exported {out_path}")


def remove_cursor_rules(repo_root: Path, dry_run: bool = False) -> None:
    """Remove Cursor .mdc files that correspond to agent markdown files.

    Args:
        repo_root: Repository root directory
        dry_run: If True, only print what would be done
    """
    agents_dir = get_agents_dir()
    out_dir = repo_root / ".cursor" / "rules"

    if not out_dir.exists():
        typer.echo(f"⚠️  Directory {out_dir} does not exist - nothing to remove")
        return

    removed_count = 0
    for fname, _ in _iter_agent_files(agents_dir):
        out_path = out_dir / (fname.removesuffix(".md") + ".mdc")

        if out_path.exists():
            if dry_run:
                typer.echo(f"[DRY] delete {out_path}")
            else:
                out_path.unlink()
                typer.echo(f"🗑️  Deleted {out_path}")
            removed_count += 1

    if removed_count == 0:
        typer.echo("⚠️  No Cursor rules found to remove")
