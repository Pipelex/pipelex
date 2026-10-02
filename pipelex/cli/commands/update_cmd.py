"""``pipelex update`` — bring the kit-managed files of an installation up to date with the kit-shipped templates.

Two areas are managed, each with its own manifest (see ``pipelex.cogt.models.deck_manifest``): the numbered
model deck files, and ``backends/internal.toml``, which declares the software-only models open Pipelex ships, so
an existing install receives the ones a release adds. ``x_custom_*.toml`` deck files and every other backend file
are user-owned and never touched. Locally-modified managed files are backed up to ``<file>.bak.<UTC-timestamp>``
before being overwritten, unless ``--no-backup`` is passed.
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from pipelex.cogt.models.deck_manifest import (
    DeckFileStatus,
    DeckSyncReport,
    KitManagedArea,
    compute_kit_manifest,
    compute_sync_report,
    kit_area_dir,
    status_rich_label,
    suggest_x_custom_filename,
    write_manifest,
)
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.config_loader import config_manager


class _AreaUpdate(NamedTuple):
    """One kit-managed area of this update: where it is installed, and how it compares to the kit."""

    area: KitManagedArea
    installed_dir: Path
    report: DeckSyncReport


def update_cmd(
    *,
    local: bool = False,
    yes: bool = False,
    dry_run: bool = False,
    no_backup: bool = False,
) -> None:
    """Apply pending updates of the kit-managed files from the running pipelex's kit.

    Args:
        local: Update the project-local ``.pipelex/`` instead of the resolved layered config dir.
        yes: Skip the interactive confirmation.
        dry_run: Print the planned actions without modifying any file.
        no_backup: Do not create ``.bak`` files for locally-modified managed files.
    """
    console = get_console()
    deck_dir = _resolve_deck_dir(local=local)
    if not deck_dir.exists():
        console.print()
        console.print(f"[red]✗[/red] No deck directory found at [cyan]{escape(str(deck_dir))}[/cyan].\nRun [cyan]pipelex init[/cyan] first.")
        console.print()
        sys.exit(1)

    area_dirs: list[tuple[KitManagedArea, Path]] = [(KitManagedArea.DECK, deck_dir)]
    # The backends directory resolves on its own, as boot resolves it: a project `.pipelex/` that carries a deck but
    # no backends reads the global ones, and that is the internal.toml to refresh. A directory that does not exist is
    # an installation `pipelex init` has not set up, which is `init`'s to fix, not this command's.
    backends_dir = _resolve_backends_dir(local=local)
    if backends_dir.is_dir():
        area_dirs.append((KitManagedArea.BACKENDS, backends_dir))

    area_updates = [
        _AreaUpdate(area=area, installed_dir=installed_dir, report=compute_sync_report(installed_dir, area=area)) for area, installed_dir in area_dirs
    ]
    for area_update in area_updates:
        _print_status_table(area_update.report, area=area_update.area, installed_dir=area_update.installed_dir)

    pending_updates = [area_update for area_update in area_updates if not area_update.report.is_clean()]
    if not pending_updates:
        console.print(_summary_panel("Model deck and internal backend are up to date.", style="green"))
        console.print()
        return

    for area_update in pending_updates:
        if not area_update.report.manifest_present:
            # Migration: surface what we found so the user can review before we materialize a baseline.
            console.print(
                f"[dim]No {escape(area_update.area.display_name.lower())} manifest found — this looks like an existing install. "
                "Running [cyan]pipelex update[/cyan] will install the latest kit content and write a baseline manifest.[/dim]"
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

    actions_applied = 0
    for area_update in pending_updates:
        actions_applied += _apply_updates(area_update.installed_dir, area=area_update.area, report=area_update.report, no_backup=no_backup)
        write_manifest(compute_kit_manifest(area=area_update.area), installed_dir=area_update.installed_dir)

    console.print()
    console.print(_summary_panel(f"Kit-managed files updated ({actions_applied} file change(s) applied).", style="green"))
    console.print()


def _resolve_deck_dir(*, local: bool) -> Path:
    """Pick the deck directory to operate on, mirroring the ``--local`` semantics of ``pipelex init``."""
    if local:
        return _local_inference_dir() / "deck"
    # Match runtime resolution: fall through to the global deck when the project .pipelex/
    # does not contain inference/deck, so update targets the deck actually in use.
    return config_manager.model_decks_dir_path


def _resolve_backends_dir(*, local: bool) -> Path:
    """Pick the backends directory to operate on, the way ``_resolve_deck_dir`` picks the deck's."""
    if local:
        return _local_inference_dir() / "backends"
    # Match runtime resolution, as for the deck: the backends directory boot actually reads.
    return config_manager.backends_dir_path


def _local_inference_dir() -> Path:
    """The project-local ``.pipelex/inference/`` directory, for ``--local``."""
    project_root = config_manager.project_root
    base = project_root / ".pipelex" if project_root is not None else Path.cwd() / ".pipelex"
    return base / "inference"


def _print_status_table(report: DeckSyncReport, *, area: KitManagedArea, installed_dir: Path) -> None:
    """Render the per-file sync status of one area as a Rich table."""
    table = Table(title=f"Pipelex {area.display_name} — Update Plan", show_lines=False)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Action")

    for filename in sorted(report.files):
        status = report.files[filename]
        table.add_row(filename, status_rich_label(status), _action_description(status))

    get_console().print()
    get_console().print(f"{area.display_name} directory: [cyan]{escape(str(installed_dir))}[/cyan]")
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


def _local_edits_tip(*, area: KitManagedArea, filename: str) -> str:
    """Where edits the update overwrote belong, so the next update leaves them in place."""
    match area:
        case KitManagedArea.DECK:
            x_custom_filename = escape(suggest_x_custom_filename(filename))
            return f"Tip: move custom aliases/presets into [cyan]{x_custom_filename}[/cyan] so future updates leave them in place."
        case KitManagedArea.BACKENDS:
            return "Tip: declare your own models in a backend of your own, so future updates leave them in place."


def _apply_updates(installed_dir: Path, *, area: KitManagedArea, report: DeckSyncReport, no_backup: bool) -> int:
    """Apply the per-file actions described by ``report`` to one area. Returns the count of files changed."""
    kit_dir = kit_area_dir(area=area)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    actions_applied = 0

    for filename in sorted(report.files):
        status = report.files[filename]
        installed_path = installed_dir / filename
        kit_path = kit_dir / filename

        match status:
            case DeckFileStatus.UP_TO_DATE:
                continue
            case DeckFileStatus.KIT_ADDED:
                installed_dir.mkdir(parents=True, exist_ok=True)
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
                get_console().print(f"    [dim]{_local_edits_tip(area=area, filename=filename)}[/dim]")
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
