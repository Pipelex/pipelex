"""Command to regenerate the migration golden chain for every configuration surface.

Writes each surface's fingerprint and complete reference document for the schema version its
ledger currently declares. Older versions are never rewritten — a bump leaves the previous
version's snapshot behind as the frozen history the chain is made of.

The regeneration diff is the point. A fingerprint golden is checked in so that a reviewer sees,
line by line, which paths a change added, removed or renamed; running this command without reading
its diff throws away the only signal it produces.
"""

import sys

from rich.markup import escape

from pipelex.migration.exceptions import MigrationError
from pipelex.migration.snapshot import snapshot_registry
from pipelex.migration.surfaces import build_config_surface_registry, packaged_migration_dir
from pipelex.runtime_hub import get_console


def update_migration_schemas_cmd(*, quiet: bool = False) -> None:
    """Regenerate the fingerprint and defaults goldens for every configuration surface.

    Args:
        quiet: If True, output only a single status line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Updating migration schema goldens...[/bold]")
        console.print()

    registry = build_config_surface_registry()
    try:
        snapshots = snapshot_registry(registry=registry, migration_dir=packaged_migration_dir())
    except MigrationError as exc:
        console.print(f"[red]✗ Migration schema update: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)

    if not quiet:
        for snapshot in snapshots:
            console.print(
                f"  [yellow]{escape(snapshot.surface_id)}[/yellow] [dim]schema {snapshot.schema_version}[/dim] - {snapshot.path_count} paths"
            )
            console.print(f"    {escape(str(snapshot.fingerprint_path))}")
            console.print(f"    {escape(str(snapshot.defaults_path))}")
        console.print()

    console.print(f"[green]✓ Migration schema update: DONE[/green] - {len(snapshots)} surfaces snapshotted")
