from pathlib import Path

import typer

from pipelex.kit.paths import get_migrations_dir


def export_migration_instructions(repo_root: Path, dry_run: bool = False) -> None:
    """Export migration documentation files to user's .pipelex/migrations directory.

    Args:
        repo_root: Repository root directory
        dry_run: If True, only print what would be done
    """
    migrations_dir = get_migrations_dir()
    out_dir = repo_root / ".pipelex" / "migrations"
    out_dir.mkdir(parents=True, exist_ok=True)

    for child in migrations_dir.iterdir():
        if child.name.endswith(".md") and child.is_file():
            content = child.read_text(encoding="utf-8")
            out_path = out_dir / child.name

            if dry_run:
                typer.echo(f"[DRY] write {out_path}")
            else:
                out_path.write_text(content, encoding="utf-8")
                typer.echo(f"✅ Copied {child.name}")
