"""``pipelex update`` — bring the installed model deck up to date with the kit-shipped templates.

Numbered deck files are managed by pipelex. ``x_custom_*.toml`` files are user-owned and never
touched. Locally-modified numbered files are backed up to ``<file>.bak.<UTC-timestamp>`` before
being overwritten, unless ``--no-backup`` is passed.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from pipelex.cogt.models.deck_manifest import (
    DeckFileStatus,
    DeckSyncReport,
    compute_deck_sync_report,
    compute_kit_manifest,
    kit_deck_dir,
    status_rich_label,
    suggest_x_custom_filename,
    write_manifest,
)
from pipelex.hub import get_console
from pipelex.system.configuration.config_loader import config_manager


def update_cmd(
    local: bool = False,
    yes: bool = False,
    dry_run: bool = False,
    no_backup: bool = False,
) -> None:
    """Apply pending model-deck updates from the running pipelex's kit.

    Args:
        local: Update the project-local ``.pipelex/`` instead of the resolved layered config dir.
        yes: Skip the interactive confirmation.
        dry_run: Print the planned actions without modifying any file.
        no_backup: Do not create ``.bak`` files for locally-modified numbered deck files.
    """
    console = get_console()
    deck_dir = _resolve_deck_dir(local=local)
    if not deck_dir.exists():
        console.print()
        console.print(f"[red]✗[/red] No deck directory found at [cyan]{escape(str(deck_dir))}[/cyan].\nRun [cyan]pipelex init[/cyan] first.")
        console.print()
        sys.exit(1)

    report = compute_deck_sync_report(deck_dir)
    _print_status_table(report, deck_dir)

    if report.is_clean():
        console.print(_summary_panel("Model deck is up to date.", style="green"))
        console.print()
        return

    if not report.manifest_present:
        # Migration: surface what we found so the user can review before we materialize a baseline.
        console.print(
            "[dim]No deck manifest found — this looks like an existing install. Running [cyan]pipelex update[/cyan] "
            "will install the latest deck content and write a baseline manifest.[/dim]"
        )
        console.print()

    if dry_run:
        console.print("[dim]Dry run — no changes written.[/dim]")
        console.print()
        return

    if not yes and not Confirm.ask("[bold]Apply these updates?[/bold]", default=True):
        console.print("[yellow]Update cancelled.[/yellow]")
        console.print()
        return

    actions_applied = _apply_updates(deck_dir=deck_dir, report=report, no_backup=no_backup)
    write_manifest(deck_dir, manifest=compute_kit_manifest())

    console.print()
    console.print(_summary_panel(f"Model deck updated ({actions_applied} file change(s) applied).", style="green"))
    console.print()


def _resolve_deck_dir(local: bool) -> Path:
    """Pick the deck directory to operate on, mirroring the ``--local`` semantics of ``pipelex init``."""
    if local:
        project_root = config_manager.project_root
        base = project_root / ".pipelex" if project_root is not None else Path.cwd() / ".pipelex"
        return base / "inference" / "deck"
    # Match runtime resolution: fall through to the global deck when the project .pipelex/
    # does not contain inference/deck, so update targets the deck actually in use.
    return config_manager.model_decks_dir_path


def _print_status_table(report: DeckSyncReport, deck_dir: Path) -> None:
    """Render the per-file sync status as a Rich table."""
    table = Table(title="Pipelex Model Deck — Update Plan", show_lines=False)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Action")

    for filename in sorted(report.files):
        status = report.files[filename]
        table.add_row(filename, status_rich_label(status), _action_description(status))

    get_console().print()
    get_console().print(f"Deck directory: [cyan]{escape(str(deck_dir))}[/cyan]")
    installed_version_label = report.installed_kit_version or "(none)"
    get_console().print(
        f"Installed kit version: [cyan]{escape(installed_version_label)}[/cyan]   Kit version: [cyan]{escape(report.kit_version)}[/cyan]"
    )
    get_console().print()
    get_console().print(table)
    get_console().print()


def _action_description(status: DeckFileStatus) -> str:
    match status:
        case DeckFileStatus.UP_TO_DATE:
            return "—"
        case DeckFileStatus.KIT_ADDED:
            return "install from kit"
        case DeckFileStatus.KIT_REMOVED:
            return "back up + remove"
        case DeckFileStatus.CLEAN_BEHIND:
            return "overwrite from kit"
        case DeckFileStatus.LOCALLY_MODIFIED:
            return "back up + overwrite from kit"


def _apply_updates(deck_dir: Path, report: DeckSyncReport, no_backup: bool) -> int:
    """Apply the per-file actions described by ``report``. Returns the count of files changed."""
    kit_dir = kit_deck_dir()
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    actions_applied = 0

    for filename in sorted(report.files):
        status = report.files[filename]
        installed_path = deck_dir / filename
        kit_path = kit_dir / filename

        match status:
            case DeckFileStatus.UP_TO_DATE:
                continue
            case DeckFileStatus.KIT_ADDED:
                deck_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(kit_path, installed_path)
                get_console().print(f"  [green]+[/green] installed [cyan]{escape(filename)}[/cyan]")
                actions_applied += 1
            case DeckFileStatus.CLEAN_BEHIND:
                shutil.copy2(kit_path, installed_path)
                get_console().print(f"  [yellow]↑[/yellow] updated [cyan]{escape(filename)}[/cyan]")
                actions_applied += 1
            case DeckFileStatus.LOCALLY_MODIFIED:
                backup_note = ""
                if not no_backup:
                    backup_path = installed_path.with_name(f"{filename}.bak.{timestamp}")
                    shutil.copy2(installed_path, backup_path)
                    backup_note = f" (backed up to [dim]{escape(backup_path.name)}[/dim])"
                shutil.copy2(kit_path, installed_path)
                get_console().print(f"  [red]↑[/red] overwrote local edits in [cyan]{escape(filename)}[/cyan]{backup_note}")
                suggested_override = suggest_x_custom_filename(filename)
                get_console().print(
                    f"    [dim]Tip: move custom aliases/presets into [cyan]{escape(suggested_override)}[/cyan] "
                    "so future updates leave them in place.[/dim]"
                )
                actions_applied += 1
            case DeckFileStatus.KIT_REMOVED:
                backup_path = installed_path.with_name(f"{filename}.bak.{timestamp}")
                shutil.copy2(installed_path, backup_path)
                installed_path.unlink()
                get_console().print(
                    f"  [yellow]-[/yellow] removed [cyan]{escape(filename)}[/cyan] (backed up to [dim]{escape(backup_path.name)}[/dim])"
                )
                actions_applied += 1

    return actions_applied


def _summary_panel(message: str, *, style: str) -> Panel:
    return Panel(message, border_style=style, padding=(1, 2))
