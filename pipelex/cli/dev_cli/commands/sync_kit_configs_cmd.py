"""Command to mirror .pipelex/ into pipelex/kit/configs/."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from pipelex.hub import get_console
from pipelex.kit.paths import CONFIG_SYNC_EXCLUDED_FILES, GIT_IGNORED_CONFIG_DIRS
from pipelex.tools.misc.file_utils import MirrorDirResult, mirror_dir

PIPELEX_DIR = ".pipelex"
KIT_CONFIGS_DIR = "pipelex/kit/configs"


def _display_result(result: MirrorDirResult, quiet: bool) -> None:
    """Display the outcome of the kit config sync."""
    console = get_console()
    prefix = "(dry run) " if result.dry_run else ""
    deleted_count = len(result.deleted_files) + len(result.deleted_dirs)

    if quiet:
        if result.has_changes:
            console.print(f"[green]✓ Kit config sync:[/green] {prefix}{len(result.copied_files)} copied, {deleted_count} deleted")
        else:
            console.print(f"[green]✓ Kit config sync:[/green] {prefix}already in sync")
        return

    console.print()
    console.print(f"[bold]Syncing kit configs[/bold] [cyan]{PIPELEX_DIR}[/cyan] [bold]→[/bold] [cyan]{KIT_CONFIGS_DIR}[/cyan]")
    console.print()

    if not result.has_changes:
        console.print(
            Panel(
                f"[green]✓[/green] {prefix}Kit configs already in sync — nothing to copy or delete.",
                title="[bold green]Kit Config Sync: NO CHANGES[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print()
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Change", style="bold")
    table.add_column("Path", style="cyan")
    for path in result.copied_files:
        table.add_row("[green]copied[/green]", path)
    for path in result.deleted_dirs:
        table.add_row("[red]deleted dir[/red]", path)
    for path in result.deleted_files:
        table.add_row("[red]deleted[/red]", path)
    console.print(table)
    console.print()

    summary = f"{len(result.copied_files)} file(s) copied, {len(result.deleted_files)} file(s) and {len(result.deleted_dirs)} dir(s) deleted."
    if result.dry_run:
        title = "Kit Config Sync: PREVIEW"
        summary += "\n[dim]Run without --dry-run to apply.[/dim]"
    else:
        title = "Kit Config Sync: DONE"
    console.print(
        Panel(
            f"[green]{prefix}{summary}[/green]",
            title=f"[bold green]{title}[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def sync_kit_configs_cmd(quiet: bool = False, dry_run: bool = False) -> None:
    """Mirror the .pipelex/ directory into pipelex/kit/configs/.

    Copies new and changed files and deletes files absent from .pipelex/, using
    the same exclude sets that `check-config-sync` enforces — so a sync is always
    followed by a passing check.

    Args:
        quiet: If True, output only a single status line.
        dry_run: If True, report what would change without touching the filesystem.
    """
    console = get_console()

    source_dir = Path(PIPELEX_DIR)
    if not source_dir.exists():
        if quiet:
            console.print(f"[red]✗ Kit config sync: FAILED[/red] - {PIPELEX_DIR} does not exist")
        else:
            console.print()
            console.print(f"[red]✗[/red] Directory [cyan]{PIPELEX_DIR}[/cyan] does not exist")
            console.print()
        sys.exit(1)

    try:
        result = mirror_dir(
            source_dir=source_dir,
            target_dir=Path(KIT_CONFIGS_DIR),
            exclude_files=CONFIG_SYNC_EXCLUDED_FILES,
            exclude_dirs=GIT_IGNORED_CONFIG_DIRS,
            dry_run=dry_run,
        )
    except OSError as exc:
        # Surface filesystem errors (permissions, races) from the mirror walk or
        # the underlying copy/delete operations.
        if quiet:
            console.print(f"[red]✗ Kit config sync: FAILED[/red] - File system error: {escape(str(exc))}")
        else:
            console.print()
            console.print(f"[red]✗[/red] File system error while syncing kit configs: {escape(str(exc))}")
            console.print()
        sys.exit(1)

    _display_result(result, quiet=quiet)
