from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.common import is_pipelex_libraries_folder
from pipelex.migration.migrate_v0_1_0_to_v0_2_0 import TOMLMigrator, migrate_concept_syntax
from pipelex.migration.migration_result import MigrationResult


def do_migrate(
    target_path: str = "./pipelex_libraries",
    dry_run: bool = False,
    backups: bool = True,
) -> None:
    """Migrate TOML files to new syntax (Concept = -> definition = and PipeClassName = -> type/definition).

    The path can be:
    - A Pipelex libraries folder (we'll use its `pipelines` subfolder)
    - A directory containing TOML files
    - A single TOML file
    """
    config_path = Path(target_path)

    if is_pipelex_libraries_folder(target_path):
        pipelines_dir_or_file = config_path / "pipelines"
    else:
        pipelines_dir_or_file = config_path

    if not pipelines_dir_or_file.exists():
        typer.echo(f"❌ Path not found at '{pipelines_dir_or_file}'")
        raise typer.Exit(1)

    try:
        result: MigrationResult = migrate_concept_syntax(
            directory=pipelines_dir_or_file,
            create_backups=backups and not dry_run,
            dry_run=dry_run,
        )

        for error in result.errors:
            typer.echo(f"❌ {error}")

        if result.errors and not result.files_modified:
            typer.echo("❌ Migration failed due to errors")
            raise typer.Exit(1)

        typer.echo(f"Found {result.files_processed} TOML file(s) to check")

        if result.files_modified == 0:
            typer.echo("✅ All TOML files are already using the new syntax")
            return

        if dry_run:
            migrator = TOMLMigrator()
            # For display, if a single file path was provided, show relative to its parent
            base_for_print = pipelines_dir_or_file if pipelines_dir_or_file.is_dir() else pipelines_dir_or_file.parent
            for file_path in result.modified_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    changes = migrator.get_migration_preview(content)
                    try:
                        rel = file_path.relative_to(base_for_print)
                    except Exception:
                        rel = Path(file_path.name)
                    typer.echo(f"\n📄 {rel}:")
                    for change in changes:
                        typer.echo(f"  Line {change['line_number']}: {change['old_line']} → {change['new_line']}")
                except Exception as exc:
                    typer.echo(f"❌ Error reading {file_path}: {exc}")

            typer.echo(f"\n📋 Summary: Found {result.total_changes} change(s) in {result.files_modified} file(s)")
            typer.echo("   Run without --dry-run to apply these changes")
        else:
            create_backups = backups and not dry_run
            base_for_print = pipelines_dir_or_file if pipelines_dir_or_file.is_dir() else pipelines_dir_or_file.parent
            for file_path in result.modified_files:
                try:
                    rel = file_path.relative_to(base_for_print)
                except Exception:
                    rel = Path(file_path.name)
                typer.echo(f"✅ Migrated {rel}")
                if create_backups:
                    backup_path = file_path.with_suffix(".toml.backup")
                    typer.echo(f"   Backup saved to {backup_path.name}")

            typer.echo(f"\n✅ Migration completed: {result.total_changes} change(s) applied to {result.files_modified} file(s)")
            if create_backups:
                typer.echo("   Backup files created with .backup extension")
            typer.echo("   Run 'pipelex validate all -c pipelex/libraries' to verify the migration")
    except FileNotFoundError as exc:
        typer.echo(f"❌ {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Migration failed: {exc}")
        raise typer.Exit(1)


# Typer group for migration commands
migrate_app = typer.Typer(help="Migration commands", no_args_is_help=True)


@migrate_app.command("run")
def migrate_cmd(
    target_path: Annotated[
        str,
        typer.Option(
            "--path",
            "-p",
            help=("Path to Pipelex libraries folder (uses its pipelines), a directory of TOML files, or a single TOML file"),
        ),
    ] = "./pipelex_libraries",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without applying them")] = False,
    backups: Annotated[bool, typer.Option("--backups/--no-backups", help="Create backup files before migration")] = False,
) -> None:
    do_migrate(target_path=target_path, dry_run=dry_run, backups=backups)
