"""Export agent markdown files to Cursor rules with YAML front-matter."""

from collections.abc import Iterable
from importlib.abc import Traversable
from pathlib import Path
from typing import Any

import typer
import yaml

from pipelex.kit.index_models import KitIndex


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
    base = dict(idx.cursor.front_matter)
    key = name.removesuffix(".md")
    if key in idx.cursor.files:
        base |= idx.cursor.files[key].front_matter
    return base


def export_cursor_rules(agents_dir: Traversable, out_dir: Path, idx: KitIndex, dry_run: bool = False) -> None:
    """Export agent markdown files to Cursor .mdc files with YAML front-matter.

    Args:
        agents_dir: Traversable pointing to agents directory
        out_dir: Output directory for .mdc files
        idx: Kit index configuration
        dry_run: If True, only print what would be done
    """
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
