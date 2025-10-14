"""CLI commands for kit asset management."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from pipelex.exceptions import PipelexCLIError
from pipelex.kit.cursor_export import export_cursor_rules, remove_cursor_rules
from pipelex.kit.index_loader import load_index
from pipelex.kit.migrations_export import export_migration_instructions
from pipelex.kit.targets_update import build_merged_rules, remove_from_targets, update_targets

kit_app = typer.Typer(help="Manage kit assets: export Cursor rules and merge agent docs", no_args_is_help=True)


@kit_app.command("rules")
def agent_rules(
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

        if cursor:
            typer.echo("📤 Exporting Cursor rules...")
            export_cursor_rules(repo_root, idx, dry_run=dry_run)

        if single_files:
            typer.echo("📝 Building merged agent documentation...")
            merged_md = build_merged_rules(idx)
            typer.echo("📝 Updating target files...")
            update_targets(repo_root, merged_md, idx.agent_rules.targets, dry_run=dry_run, diff=diff, backup=backup)

        if dry_run:
            typer.echo("✅ Dry run completed - no changes made")
        else:
            typer.echo("✅ Kit sync completed successfully")

    except Exception as exc:
        msg = f"Failed to sync kit assets for agent rules: {exc}"
        raise PipelexCLIError(msg) from exc


@kit_app.command("remove-rules")
def remove_rules(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    cursor: Annotated[bool, typer.Option("--cursor/--no-cursor", help="Remove Cursor rules from .cursor/rules")] = True,
    single_files: Annotated[bool, typer.Option("--single-files/--no-single-files", help="Remove agent documentation from target files")] = True,
    delete_files: Annotated[bool, typer.Option("--delete-files", help="Delete entire target files instead of just removing marked sections")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
    diff: Annotated[bool, typer.Option("--diff", help="Show unified diff of changes")] = False,
    backup: Annotated[str | None, typer.Option("--backup", help="Backup suffix (e.g., '.bak')")] = None,
) -> None:
    """Remove agent rules: delete Cursor rules and remove marked sections from target files.

    This command:
    1. Deletes agent markdown files from Cursor .mdc files in .cursor/rules
    2. Removes marked sections from target files (or deletes entire files with --delete-files)
    """
    try:
        if repo_root is None:
            repo_root = Path()

        idx = load_index()

        if cursor:
            typer.echo("🗑️  Removing Cursor rules...")
            remove_cursor_rules(repo_root, dry_run=dry_run)

        if single_files:
            if delete_files:
                typer.echo("🗑️  Deleting target files...")
            else:
                typer.echo("🗑️  Removing marked sections from target files...")
            remove_from_targets(
                repo_root,
                idx.agent_rules.targets,
                delete_files=delete_files,
                dry_run=dry_run,
                diff=diff,
                backup=backup,
            )

        if dry_run:
            typer.echo("✅ Dry run completed - no changes made")
        else:
            typer.echo("✅ Agent rules removal completed successfully")

    except Exception as exc:
        msg = f"Failed to remove agent rules: {exc}"
        raise PipelexCLIError(msg) from exc


@kit_app.command("migrations")
def migration_instructions(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
) -> None:
    """Sync migration instructions from kit to .pipelex/migrations.

    This command copies migration documentation files from the pipelex.kit
    package to the user's .pipelex/migrations directory.
    """
    try:
        if repo_root is None:
            repo_root = Path()

        typer.echo("📄 Syncing migration instructions...")
        export_migration_instructions(repo_root, dry_run=dry_run)

        if dry_run:
            typer.echo("✅ Dry run completed - no changes made")
        else:
            typer.echo(f"✅ Migration instructions synced to {repo_root / '.pipelex' / 'migrations'}")

    except Exception as exc:
        msg = f"Failed to sync migration instructions: {exc}"
        raise PipelexCLIError(msg) from exc
