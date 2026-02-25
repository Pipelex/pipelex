"""Command to sync main config values to kit and project configs."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from pipelex.hub import get_console
from pipelex.tools.misc.toml_sync import TomlSyncResult, sync_toml_values
from pipelex.types import StrEnum

# Config file paths
MAIN_CONFIG_PATH = "pipelex/pipelex.toml"
KIT_CONFIG_PATH = "pipelex/kit/configs/pipelex.toml"
PROJECT_CONFIG_PATH = ".pipelex/pipelex.toml"


class SyncTarget(StrEnum):
    """Target for syncing config values."""

    KIT = "kit"
    PROJECT = "project"
    ALL = "all"


def _format_value(value: object) -> str:
    """Format a value for display, truncating if too long."""
    str_value = repr(value)
    if len(str_value) > 50:
        return str_value[:47] + "..."
    return str_value


def _display_sync_result(
    result: TomlSyncResult,
    target_label: str,
    show_diff: bool,
    quiet: bool,
) -> None:
    """Display the result of a sync operation."""
    console = get_console()

    if quiet:
        if result.updated_count > 0:
            console.print(f"[green]Synced[/green] {target_label}: {result.updated_count} updated, {result.unchanged_count} unchanged")
        else:
            console.print(f"[dim]Synced[/dim] {target_label}: no changes needed")
        return

    if result.updated_count == 0:
        console.print(f"  [dim]No changes needed for[/dim] [cyan]{target_label}[/cyan]")
        return

    console.print(f"  [green]Updated[/green] [cyan]{target_label}[/cyan]: {result.updated_count} keys")

    if show_diff and result.changes:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Old Value", style="red")
        table.add_column("New Value", style="green")

        for change in result.changes:
            table.add_row(
                change.key_path,
                _format_value(change.old_value),
                _format_value(change.new_value),
            )

        console.print(table)


def sync_main_config_cmd(
    target: SyncTarget = SyncTarget.ALL,
    dry_run: bool = False,
    quiet: bool = False,
    show_diff: bool = True,
) -> None:
    """Sync values from main config to kit and/or project configs.

    Args:
        target: Which target(s) to sync to: 'kit', 'project', or 'all'
        dry_run: If True, show what would change without applying
        quiet: If True, output only minimal validation lines
        show_diff: If True, display detailed changes
    """
    console = get_console()

    # Check if main config exists
    main_path = Path(MAIN_CONFIG_PATH)
    if not main_path.exists():
        if quiet:
            console.print(f"[red]Error:[/red] Main config not found: {MAIN_CONFIG_PATH}")
        else:
            console.print()
            console.print(f"[red]Error:[/red] Main config not found: [cyan]{MAIN_CONFIG_PATH}[/cyan]")
            console.print()
        sys.exit(1)

    # Determine which targets to sync
    sync_kit = target in {SyncTarget.KIT, SyncTarget.ALL}
    sync_project = target in {SyncTarget.PROJECT, SyncTarget.ALL}

    if not quiet:
        mode_label = "[yellow](dry run)[/yellow]" if dry_run else ""
        console.print()
        console.print(f"[bold]Syncing main config values {mode_label}[/bold]")
        console.print(f"  Source: [cyan]{MAIN_CONFIG_PATH}[/cyan]")
        console.print()

    results: list[tuple[str, TomlSyncResult | None, str]] = []

    # Sync to kit config
    if sync_kit:
        kit_path = Path(KIT_CONFIG_PATH)
        if kit_path.exists():
            try:
                kit_result = sync_toml_values(MAIN_CONFIG_PATH, KIT_CONFIG_PATH, dry_run=dry_run)
                results.append(("kit", kit_result, KIT_CONFIG_PATH))
            except OSError as exc:
                # Handle race condition where file is deleted/modified after exists() check
                if quiet:
                    console.print(f"[red]Error:[/red] File system error syncing kit config: {escape(str(exc))}")
                else:
                    console.print(f"  [red]Error:[/red] File system error syncing kit config: {escape(str(exc))}")
                sys.exit(1)
        else:
            if not quiet:
                console.print(f"  [yellow]Skipped[/yellow] kit config: [cyan]{KIT_CONFIG_PATH}[/cyan] not found")
            results.append(("kit", None, KIT_CONFIG_PATH))

    # Sync to project config
    if sync_project:
        project_path = Path(PROJECT_CONFIG_PATH)
        if project_path.exists():
            try:
                project_result = sync_toml_values(MAIN_CONFIG_PATH, PROJECT_CONFIG_PATH, dry_run=dry_run)
                results.append(("project", project_result, PROJECT_CONFIG_PATH))
            except OSError as exc:
                # Handle race condition where file is deleted/modified after exists() check
                if quiet:
                    console.print(f"[red]Error:[/red] File system error syncing project config: {escape(str(exc))}")
                else:
                    console.print(f"  [red]Error:[/red] File system error syncing project config: {escape(str(exc))}")
                sys.exit(1)
        else:
            if not quiet:
                console.print(f"  [yellow]Skipped[/yellow] project config: [cyan]{PROJECT_CONFIG_PATH}[/cyan] not found")
            results.append(("project", None, PROJECT_CONFIG_PATH))

    # Display results
    total_updated = 0
    for label, result, path in results:
        if result is not None:
            _display_sync_result(result, f"{label} ({path})", show_diff=show_diff, quiet=quiet)
            total_updated += result.updated_count

    if not quiet:
        console.print()
        if dry_run:
            if total_updated > 0:
                dry_run_msg = (
                    "[yellow]Dry run complete[/yellow]\n\n"
                    f"{total_updated} key(s) would be updated.\n"
                    "[dim]Run without --dry-run to apply changes.[/dim]"
                )
                panel = Panel(
                    dry_run_msg,
                    title="[bold yellow]Preview Only[/bold yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                )
            else:
                panel = Panel(
                    "[green]All configs are already in sync.[/green]",
                    title="[bold green]No Changes Needed[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            console.print(panel)
        else:
            if total_updated > 0:
                panel = Panel(
                    f"[green]Sync complete![/green]\n\n{total_updated} key(s) updated.",
                    title="[bold green]Config Sync Complete[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            else:
                panel = Panel(
                    "[green]All configs are already in sync.[/green]",
                    title="[bold green]No Changes Needed[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            console.print(panel)
        console.print()
