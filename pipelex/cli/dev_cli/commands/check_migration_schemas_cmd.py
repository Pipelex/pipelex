"""Command to verify that every configuration surface has accounted for its schema changes.

This is the coverage half of the migration gate. It reads the checked-in ledgers and golden
chains, recomputes each surface's fingerprint, and fails when a schema change would leave a user's
file broken with nothing written down about how to repair it.

It lives in `make check` and deliberately **not** in `make agent-check`: it is a golden check, and
in the loop agents run constantly a fail-regenerate-fail cycle with no single right answer is how
a gate goes permanently green while catching nothing.
"""

import sys

from pipelex.migration.coverage import CoverageIssue, check_registry
from pipelex.migration.exceptions import MigrationError
from pipelex.migration.surfaces import build_config_surface_registry, packaged_migration_dir
from pipelex.runtime_hub import get_console


def check_migration_schemas_cmd(*, quiet: bool = False) -> None:
    """Verify that every configuration surface's schema changes are accounted for.

    Args:
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking migration schema coverage...[/bold]")
        console.print()

    registry = build_config_surface_registry()
    try:
        issues = check_registry(registry=registry, migration_dir=packaged_migration_dir())
    except MigrationError as exc:
        console.print(f"[red]✗ Migration schema check: FAILED[/red] - {exc}")
        sys.exit(1)

    if not issues:
        surface_count = len(registry.surfaces)
        console.print(f"[green]✓ Migration schema check: PASSED[/green] - {surface_count} surfaces accounted for")
        return

    _print_issues(issues=issues, quiet=quiet)
    sys.exit(1)


def _print_issues(*, issues: list[CoverageIssue], quiet: bool) -> None:
    console = get_console()
    console.print(f"[red]✗ Migration schema check: FAILED[/red] - {len(issues)} issues")
    if quiet:
        console.print("  Run [cyan]make cmig[/cyan] for the full report.")
        return
    console.print()
    for issue in issues:
        console.print(f"  [yellow]{issue.surface_id}[/yellow] [dim]({issue.kind})[/dim]")
        console.print(f"    {issue.message}")
        console.print()
