"""CLI commands for kit asset management."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.kit.cursor_rules import remove_cursor_rules, update_cursor_rules
from pipelex.kit.index_loader import load_index
from pipelex.kit.index_models import KitIndex
from pipelex.kit.migrations_export import export_migration_instructions
from pipelex.kit.single_file_agent_rules import remove_from_targets, update_single_file_agent_rules

kit_app = typer.Typer(no_args_is_help=True)


def _sync_agent_rules(
    repo_root: Path | None,
    cursor: bool,
    single_files: bool,
    dry_run: bool,
    diff: bool,
    backup: str | None,
    agent_set: str | None,
    kit_index: KitIndex | None = None,
) -> None:
    resolved_repo_root = repo_root if repo_root is not None else Path()
    loaded_kit_index = load_index() if kit_index is None else kit_index
    agent_set = agent_set or loaded_kit_index.agent_rules.default_set

    if cursor:
        typer.echo("📤 Updating Cursor rules...")
        update_cursor_rules(resolved_repo_root, loaded_kit_index, agent_set=agent_set, dry_run=dry_run)

    if single_files:
        typer.echo("📝 Updating target files...")
        update_single_file_agent_rules(
            repo_root=resolved_repo_root,
            kit_index=loaded_kit_index,
            agent_set=agent_set,
            targets=loaded_kit_index.agent_rules.targets,
            dry_run=dry_run,
            diff=diff,
            backup=backup,
        )

    if dry_run:
        typer.echo("✅ Dry run completed - no changes made")
    else:
        typer.echo("✅ Kit sync completed successfully")


@kit_app.command("rules", help="Export Pipelex Cursor rules and merge Pipelex marked sections into other agent rules files")
def agent_rules(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    cursor: Annotated[bool, typer.Option("--cursor/--no-cursor", help="Export Cursor rules to .cursor/rules")] = True,
    single_files: Annotated[bool, typer.Option("--single-files/--no-single-files", help="Update single-file agent documentation targets")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
    diff: Annotated[bool, typer.Option("--diff", help="Show unified diff of changes")] = False,
    backup: Annotated[str | None, typer.Option("--backup", help="Backup suffix (e.g., '.bak')")] = None,
    agent_set: Annotated[str | None, typer.Option("--set", help="Agent rule set to sync (use 'pipelex' for Pipelex repo)")] = None,
) -> None:
    try:
        _sync_agent_rules(
            repo_root=repo_root,
            cursor=cursor,
            single_files=single_files,
            dry_run=dry_run,
            diff=diff,
            backup=backup,
            agent_set=agent_set,
        )

    except Exception as exc:
        msg = f"Failed to sync kit assets for agent rules: {exc}"
        raise PipelexCLIError(msg) from exc


@kit_app.command(
    "remove-rules", help="Remove agent rules: delete Pipelex Cursor rules and remove Pipelex marked sections from other agent rules files"
)
def remove_rules(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    cursor: Annotated[bool, typer.Option("--cursor/--no-cursor", help="Remove Cursor rules from .cursor/rules")] = True,
    single_files: Annotated[bool, typer.Option("--single-files/--no-single-files", help="Remove agent documentation from target files")] = True,
    delete_files: Annotated[bool, typer.Option("--delete-files", help="Delete entire target files instead of just removing marked sections")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
    diff: Annotated[bool, typer.Option("--diff", help="Show unified diff of changes")] = False,
    backup: Annotated[str | None, typer.Option("--backup", help="Backup suffix (e.g., '.bak')")] = None,
) -> None:
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


@kit_app.command("migrations", help="Sync Pipelex migration instructions to the `.pipelex/migrations` directory")
def migration_instructions(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done without making changes")] = False,
) -> None:
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
