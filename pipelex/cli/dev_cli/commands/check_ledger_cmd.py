"""Command to verify that every migration ledger says only legal things, and replays harmlessly.

This is the static half of the migration gate. It reads the checked-in ledgers, the golden chain
and the two reference documents, and refuses an entry that would act on live material, reach into
a user's own key space, rewrite a value a user may legitimately have chosen, resurrect a retired
name, or fire on a file that is already current.

Unlike `check-migration-schemas`, it joins `make agent-check`: it fingerprints no live model and
regenerates nothing, so every failure is a statement about a file the author wrote and every
remedy is to fix one — never "regenerate the golden and move on".
"""

import sys

from rich.markup import escape

from pipelex.migration.exceptions import MigrationError
from pipelex.migration.ledger_check import LedgerIssue, check_ledgers
from pipelex.migration.surfaces import build_config_surface_registry, packaged_migration_dir
from pipelex.runtime_hub import get_console


def check_ledger_cmd(*, quiet: bool = False) -> None:
    """Verify that every configuration surface's migration ledger is legal and converges.

    Args:
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet
            only trims success output: a failure always lists every issue, because the Make
            targets invoke the check quietly and a red gate has to say what to do.
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking migration ledgers...[/bold]")
        console.print()

    registry = build_config_surface_registry()
    try:
        issues = check_ledgers(registry=registry, migration_dir=packaged_migration_dir())
    except MigrationError as exc:
        # An error is always loud — quiet only trims success output, never failures.
        console.print(f"[red]✗ Migration ledger check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)

    if not issues:
        surface_count = len(registry.surfaces)
        console.print(f"[green]✓ Migration ledger check: PASSED[/green] - {surface_count} ledgers legal and convergent")
        return

    _print_issues(issues=issues)
    sys.exit(1)


def _print_issues(*, issues: list[LedgerIssue]) -> None:
    console = get_console()
    console.print(f"[red]✗ Migration ledger check: FAILED[/red] - {len(issues)} issues")
    console.print()
    for issue in issues:
        # Messages quote ledger text and path lists, both of which can look like Rich markup.
        console.print(f"  [yellow]{escape(issue.surface_id)}[/yellow] [dim]({issue.kind})[/dim]")
        console.print(f"    {escape(issue.message)}")
        console.print()
