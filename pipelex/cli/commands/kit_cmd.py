"""CLI commands for kit asset management."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from pipelex.exceptions import PipelexCLIError
from pipelex.kit.cursor_export import export_cursor_rules
from pipelex.kit.index_loader import load_index
from pipelex.kit.paths import get_agents_dir
from pipelex.kit.targets_update import build_merged_rules, update_targets

kit_app = typer.Typer(help="Manage kit assets: export Cursor rules and merge agent docs", no_args_is_help=True)


@kit_app.command("sync")
def sync(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    cursor: Annotated[bool, typer.Option("--cursor/--no-cursor", help="Export Cursor rules to .cursor/rules")] = True,
    single_files: Annotated[bool, typer.Option("--single-files/--no-single-files", help="Update single-file agent documentation targets")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
    diff: Annotated[bool, typer.Option("--diff", help="Show unified diff of changes")] = False,
    backup: Annotated[str | None, typer.Option("--backup", help="Backup suffix (e.g., '.bak')")] = None,
) -> None:
    """Sync kit assets: export Cursor rules and merge agent documentation.

    This command:
    1. Exports agent markdown files to Cursor .mdc files with YAML front-matter
    2. Builds merged agent documentation and updates target files using markers
    """
    try:
        if repo_root is None:
            repo_root = Path()

        idx = load_index()
        agents_dir = get_agents_dir()

        if cursor:
            typer.echo("📤 Exporting Cursor rules...")
            cursor_rules_dir = repo_root / ".cursor" / "rules"
            export_cursor_rules(agents_dir, cursor_rules_dir, idx, dry_run=dry_run)

        if single_files:
            typer.echo("📝 Building merged agent documentation...")
            merged_md = build_merged_rules(agents_dir, idx)
            typer.echo("📝 Updating target files...")
            update_targets(repo_root, merged_md, idx.targets, dry_run=dry_run, diff=diff, backup=backup)

        if dry_run:
            typer.echo("✅ Dry run completed - no changes made")
        else:
            typer.echo("✅ Kit sync completed successfully")

    except Exception as exc:
        msg = f"Failed to sync kit assets: {exc}"
        raise PipelexCLIError(msg) from exc
